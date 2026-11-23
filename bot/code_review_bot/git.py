# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import asyncio
import base64
import os
import re
import tempfile
from urllib.parse import urlparse

import structlog
from git import Repo
from git.exc import GitCommandError
from libmozdata.phabricator import PhabricatorPatch
from simple_github import AppAuth, AppInstallationAuth

from code_review_bot.vcs import BaseRepository, BaseWorker

logger = structlog.getLogger(__name__)

# Default author for commits without explicit Phabricator author data, and the
# committer for all bot-created commits. Matches the Mercurial worker.
DEFAULT_AUTHOR_NAME = "code review bot"
DEFAULT_AUTHOR_EMAIL = "release-mgmt-analysis@mozilla.com"

# Matches a trailing "Weekday Mon DD HH:MM:SS YYYY +ZZZZ" timestamp that some
# Phabricator/Mercurial raw diffs append to the ---/+++ header lines. `git apply`
# would treat it as part of the filename, so it is stripped before applying.
DIFF_HEADER_TIMESTAMP = re.compile(
    r"[ \t]+\w{3}\s+\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\d{4}\s+[+-]\d{4}\s*$"
)

# Number of paths handed to one git command when checking out issue files
FILES_CHUNK = 500


def build_repo_slug(repo_url):
    """
    Build a slug from a github repository url
    mozilla-firefox/firefox would become mozilla-firefox_firefox
    This method copies the automatic slug creation in backend's RepositoryGetOrCreateField serializer field.
    """
    parts = urlparse(repo_url)
    assert parts.netloc == "github.com", "Only github repositories are supported"

    path = parts.path.lstrip("/")
    if path.endswith(".git"):
        path = path[:-4]

    return path.replace("/", "_")


def ensure_remote(repo, name, url):
    """Return the remote `name` of `repo` pointing at `url`, creating or
    updating it as needed."""
    try:
        remote = repo.remotes[name]
    except IndexError:
        return repo.create_remote(name, url)
    if remote.url != url:
        logger.info("Update remote url", remote=name, url=url)
        remote.set_url(url)
    return remote


def files_in_revision(repo, revision, paths):
    """Keep the paths that are files in `revision`: `git checkout` refuses a
    pathspec matching nothing, and a directory would bring its whole content.
    Paths are checked in chunks to keep the command lines short."""
    candidates = [
        path for path in paths if path and not path.startswith("/") and ".." not in path
    ]
    found = set()
    for start in range(0, len(candidates), FILES_CHUNK):
        chunk = candidates[start : start + FILES_CHUNK]
        out = repo.git.ls_tree("-r", "--name-only", "-z", revision, "--", *chunk)
        found.update(name for name in out.split("\0") if name)
    return [path for path in candidates if path in found]


def git_clone(base_repository, head_repository, revision, destination, paths=None):
    """
    Make the files of a pushed commit available under destination/<base slug>,
    like `cat_files` does for Mercurial: issue hashes and file existence checks
    read them from there.

    The commit is fetched by SHA from the head repository with depth 1: there
    is no need for the history, and a later force push on the same branch (the
    other analysis mode of the diff, a re-fired build) leaves it unreachable
    from any ref while GitHub still serves it by SHA, as a Mercurial try head
    stays addressable by hash. When `paths` is given, the fetch leaves the
    blobs out and only those files are checked out, so a 10 GB repository
    costs seconds instead of a full clone; with `paths` at None the whole
    working tree is checked out.
    An existing repository is reused, its previous files dropped first.
    """
    base_slug = build_repo_slug(base_repository)
    head_slug = build_repo_slug(head_repository)

    path = destination / base_slug
    if path.exists() and (path / ".git").is_dir():
        logger.info("Use existing repo", path=path)
        repo = Repo(path)
        # Drop the files of the previous revision: a stale file would pass the
        # existence check of an issue on a path the new revision does not have
        repo.git.read_tree("--empty")
        repo.git.clean("-fdxq")
    else:
        logger.info("Init git repository", path=path)
        repo = Repo.init(path)

    ensure_remote(repo, "origin", base_repository)
    head = ensure_remote(repo, head_slug, head_repository)

    logger.info("Fetch remote head", url=head.url, revision=revision)
    options = ["--depth=1"]
    if paths is not None:
        options.append("--filter=blob:none")
    repo.git.fetch(*options, head_slug, revision)

    if paths is None:
        logger.info("Checkout to head", revision=revision)
        repo.git.checkout(revision, force=True, detach=True)
        return repo

    # The checkout below reads the files from the commit itself and does not
    # need HEAD; HEAD is still detached on the commit so the cache directory
    # names the analysed revision (git log, git show) when a worker is
    # inspected, for the cost of one ref update
    repo.git.update_ref("--no-deref", "HEAD", revision)
    files = files_in_revision(repo, revision, sorted(set(paths)))
    logger.info(
        "Checkout files to head",
        revision=revision,
        files=len(files),
        requested=len(paths),
    )
    # The paths travel on the command line and a revision can carry thousands
    # of issue files (a tree-wide reformat), so they go in chunks to stay well
    # under the kernel's limit on argument size; the missing blobs are fetched
    # on the way
    for start in range(0, len(files), FILES_CHUNK):
        repo.git.checkout(revision, "--", *files[start : start + FILES_CHUNK])

    return repo


class GitRepository(BaseRepository):
    """
    A Git repository with credentials to push a patch stack to a remote
    (e.g. a GitHub "try" repository).

    Notable differences from the Mercurial implementation:
    - the base revision is already a Git hash, so there is no Lando ``git2hg`` lookup;
    - one repository holds many branches, so the branch the patches apply on
      is part of the configuration (``default_revision``) instead of a default;
    - pushes are authenticated over HTTPS with a short-lived GitHub App
      installation token generated at push time and sent as an HTTP header.
    """

    def __init__(self, config, cache_root):
        super().__init__(config, cache_root)

        # Branch template pushed to the remote try repository, rendered per
        # build so two analyses never push the same branch, not even two
        # diffs of one revision. Supported placeholders: {revision_id}, {diff_id}
        self.head_branch = (
            config.get("head_branch") or "code-review/D{revision_id}-{diff_id}"
        )
        self.push_branch = None

        # GitHub App credentials used to generate short-lived push tokens
        self.github_app_id = config.get("github_app_id")
        self.github_app_privkey = config.get("github_app_privkey")
        self._github_token = None

        # Hash of the commit the current build's patches are applied on,
        # recorded by apply_build() and handed to the decision task
        self.base_commit = None

    @property
    def repo(self):
        """Lazily open the local Git repository."""
        if self._repo is None:
            logger.info(f"Git open {self.dir}")
            self._repo = Repo(self.dir)
        return self._repo

    @property
    def default_revision(self):
        """Tip of the branch the patches apply on, as last fetched from origin
        so it follows upstream across builds."""
        return f"origin/{self.branch}"

    @default_revision.setter
    def default_revision(self, branch):
        # The branch the revision was submitted to: with every branch in one
        # repository, no default is safe
        if not branch:
            raise ValueError(
                f"Repository {self.name} needs the branch the patches apply on"
            )
        self.branch = branch

    def github_token(self):
        """Short-lived GitHub App installation token for the try repository.

        Generated on first use and cached for the run (a bot run is well within
        the one hour validity of installation tokens).
        """
        if self._github_token is None:
            assert (
                self.github_app_id and self.github_app_privkey
            ), "Missing GitHub App credentials"
            self._github_token = asyncio.run(self._generate_github_token())
        return self._github_token

    async def _generate_github_token(self):
        parts = urlparse(self.try_url)
        assert (
            parts.netloc == "github.com"
        ), "GitHub App tokens only support github.com repositories"
        path = parts.path.strip("/").removesuffix(".git")
        owner, _, repo = path.partition("/")
        auth = AppInstallationAuth(
            AppAuth(self.github_app_id, self.github_app_privkey),
            owner,
            repositories=[repo],
        )
        try:
            return await auth.get_token()
        finally:
            await auth.close()

    def push_environment(self, url):
        """Environment variables authenticating Git commands on an HTTPS url.

        The installation token travels as an Authorization header, configured
        through the environment like actions/checkout does, so it never shows
        up on a command line nor in the error messages built from one.
        Other urls (e.g. local paths in the test suite) need no credentials.
        """
        parts = urlparse(url)
        if parts.scheme not in ("http", "https"):
            return {}
        credentials = base64.b64encode(
            f"x-access-token:{self.github_token()}".encode()
        ).decode()
        return {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": f"http.{parts.scheme}://{parts.netloc}/.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {credentials}",
        }

    def clone(self):
        # Read operations use the plain url: the repositories are public, only
        # pushes need authentication
        logger.info(
            "Checking out git repository",
            repo=self.url,
            branch=self.branch,
            dir=self.dir,
        )
        if os.path.isdir(os.path.join(self.dir, ".git")):
            self._repo = Repo(self.dir)
            self.repo.remotes.origin.fetch()
        else:
            # Start on the target branch: beta, release or ESR diverge a lot
            # from the remote's default branch. Only that branch is cloned,
            # and without the file contents of its history (a blob-less
            # partial clone): the blobs of one revision are fetched when it
            # is checked out, so a Firefox clone costs about 1.7 GB instead
            # of 5 GB while short hashes and ancestry still resolve locally,
            # which keeps the pushes down to the new commits.
            self._repo = Repo.clone_from(
                self.url,
                self.dir,
                branch=self.branch,
                single_branch=True,
                filter="blob:none",
            )
        with self.repo.config_writer() as writer:
            # Negotiate the commits in common with the try repository instead
            # of trusting its advertised refs alone: the try repository is a
            # fork of upstream and holds the base revision, so the push carries
            # the new commits only, never the base revision's tree. Set on a
            # reused clone too, which may predate this setting.
            writer.set_value("push", "negotiate", "true")
        logger.info("Checkout finished")

    def has_revision(self, revision):
        """Check whether a revision exists in the local Git repository."""
        if not revision:
            return False
        try:
            self.repo.git.cat_file("-e", f"{revision}^{{commit}}")
            return True
        except GitCommandError:
            return False

    def get_base_identifier(self, needed_stack: list[PhabricatorPatch]) -> str:
        """Return the base identifier to apply patches against.

        Unlike Mercurial, the base revision is already a Git hash, so there is
        no Lando ``git2hg`` conversion. A base revision missing locally is
        handled by ``apply_build``, which records it on the build and falls
        back to the default revision.
        """
        if self.use_latest_revision:
            return self.default_revision
        return needed_stack[0].base_revision

    def update_working_copy(self, revision):
        """Move the working tree to a revision, unless it is there already.

        HEAD is detached so the patches committed on top stay throwaway drafts
        and never advance a branch.
        """
        if (
            self.repo.head.is_detached
            and self.repo.head.commit.hexsha == self.repo.commit(revision).hexsha
        ):
            return
        logger.info(f"Updating repo to revision {revision}")
        self.repo.git.checkout(revision, force=True, detach=True)

    def apply_build(self, build):
        parent = super().apply_build(build)
        # Resolved to a hash so the try_task_config.json can carry it even when
        # the base is a symbolic revision such as origin/main
        base = getattr(build, "actual_base_revision", None) or parent
        self.base_commit = self.repo.commit(base).hexsha
        return parent

    @staticmethod
    def get_author(commit):
        """Build a ``(name, email)`` tuple from Phabricator commit data."""
        author = commit.get("author") if commit else None
        if author is None:
            return DEFAULT_AUTHOR_NAME, DEFAULT_AUTHOR_EMAIL
        if author.get("name") and author.get("email"):
            return author["name"], author["email"]
        # Fall back to parsing the raw "Name <email>" representation
        raw = author.get("raw", "") or ""
        match = re.match(r"^(?P<name>.*?)\s*<(?P<email>.*)>\s*$", raw)
        if match:
            return match.group("name"), match.group("email")
        return (raw or DEFAULT_AUTHOR_NAME), DEFAULT_AUTHOR_EMAIL

    @staticmethod
    def normalize_patch(patch: str) -> str:
        """Strip trailing timestamps from ---/+++ header lines.

        Some Phabricator/Mercurial raw diffs append a "Weekday Mon DD ..." timestamp
        to the header filenames; ``git apply`` would treat it as part of the filename.
        """
        lines = []
        for line in patch.splitlines():
            if line.startswith("--- ") or line.startswith("+++ "):
                line = DIFF_HEADER_TIMESTAMP.sub("", line)
            lines.append(line)
        return "\n".join(lines) + "\n"

    def apply_patch(self, patch, message, commit, parent):
        """Apply a single unified diff on top of `parent`, commit it and
        return the new commit hash."""
        name, email = self.get_author(commit)
        self.update_working_copy(parent)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".diff", delete=False
        ) as patch_file:
            patch_file.write(self.normalize_patch(patch.patch))
            patch_path = patch_file.name

        try:
            self.repo.git.apply("--index", patch_path)
            env = {
                "GIT_AUTHOR_NAME": name,
                "GIT_AUTHOR_EMAIL": email,
                "GIT_COMMITTER_NAME": DEFAULT_AUTHOR_NAME,
                "GIT_COMMITTER_EMAIL": DEFAULT_AUTHOR_EMAIL,
            }
            with self.repo.git.custom_environment(**env):
                self.repo.git.commit("--no-verify", "-m", message)
        finally:
            os.unlink(patch_path)
        return self.repo.head.commit.hexsha

    def commit_try_task_config(self, path, message, parent):
        """Commit the try_task_config.json file as the bot on top of `parent`
        and return the new commit hash"""
        self.update_working_copy(parent)
        self.repo.git.add(path)
        env = {
            "GIT_AUTHOR_NAME": DEFAULT_AUTHOR_NAME,
            "GIT_AUTHOR_EMAIL": DEFAULT_AUTHOR_EMAIL,
            "GIT_COMMITTER_NAME": DEFAULT_AUTHOR_NAME,
            "GIT_COMMITTER_EMAIL": DEFAULT_AUTHOR_EMAIL,
        }
        with self.repo.git.custom_environment(**env):
            self.repo.git.commit("--no-verify", "-m", message)
        return self.repo.head.commit.hexsha

    def render_push_branch(self, build):
        """Render the head_branch template for a specific build."""
        try:
            return self.head_branch.format(
                revision_id=build.revision_id, diff_id=build.diff_id
            )
        except (AttributeError, IndexError, KeyError) as e:
            raise Exception(
                f"Invalid head_branch template {self.head_branch!r}: {e}"
            ) from e

    def add_try_commit(self, build, extra_parameters, parent):
        # Rendered before the try commit so a bad template fails ahead of any
        # remote interaction
        self.push_branch = self.render_push_branch(build)

        # GitHub reports no base for a push that creates the branch and the
        # previous tip for a force push, so the decision task could not tell
        # what the stack changed. Record the real base the same way `mach try`
        # does; the decision task applies these parameters before computing
        # files_changed and the taskgraph diff base.
        assert self.base_commit, "add_try_commit() called before apply_build()"
        parameters = dict(extra_parameters)
        parameters["base_rev"] = self.base_commit
        return super().add_try_commit(build, parameters, parent)

    def push_to_try(self, revision):
        """Push a commit to the remote try repository."""
        branch = self.push_branch or self.head_branch
        logger.info("Pushing patches to try", rev=revision, branch=branch)
        with self.repo.git.custom_environment(**self.push_environment(self.try_url)):
            self.repo.git.push(
                self.try_url, f"{revision}:refs/heads/{branch}", force=True
            )
        return revision

    def revision_id(self, revision):
        """Extract the revision identifier from a push_to_try result"""
        return revision

    def clean(self):
        """Reset the local checkout to a pristine state.

        Mirrors the Mercurial ``clean()`` (revert + strip outgoing drafts +
        pull): a reused clone can hold the patch commits and ``try_task_config``
        commit from a previous build, so we discard local changes, refresh from
        the remote and return to the tip of the target branch.
        """
        logger.info("Cleaning git checkout")

        # Discard uncommitted changes and untracked/ignored files
        self.repo.git.reset("--hard")
        self.repo.git.clean("-fxd")

        # Refresh from the remote (mirrors hg pull)
        self.repo.remotes.origin.fetch()

        # Return to the pristine tip of the branch, dropping any previously
        # applied commits
        target = self.default_revision
        if not self.has_revision(target):
            raise Exception(f"Branch {self.branch} is not on origin")
        self.repo.git.checkout(target, force=True, detach=True)


class GitWorker(BaseWorker):
    """
    Git worker maintaining several local clones.

    Mirrors the Mercurial worker, without the treestatus wait: Git has no
    "try" tree to gate on, so failed pushes are simply retried with backoff.
    """

    VCS_ERROR = GitCommandError
    VCS_NAME = "Git"
    FAILURE_MODE = "fail:git"
    REPOSITORY_CLASS = GitRepository

    ELIGIBLE_RETRY_ERRORS = [
        error.lower()
        for error in [
            "could not read from remote repository",
            "connection closed by remote host",
            "connection timed out",
            "early eof",
            "rpc failed",
            "the remote end hung up unexpectedly",
            "ssh_exchange_identification",
        ]
    ]

    def format_error(self, error):
        """Extract a readable error log from a Git exception"""
        return error.stderr or str(error)
