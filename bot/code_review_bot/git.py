# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import asyncio
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


def git_clone(base_repository, head_repository, revision, destination):
    """
    Clone a git repo at a specific revision in a directory
    If the repo is already present, fetches and checkout
    """

    # Build slug
    base_slug = build_repo_slug(base_repository)
    head_slug = build_repo_slug(head_repository)

    # Clone or fetch upstream
    path = destination / base_slug
    if path.exists() and (path / ".git").is_dir():
        logger.info("Use existing repo", path=path)
        repo = Repo.init(path)

        # Make sure origin matches the url
        origin = repo.remotes["origin"]
        if origin.url != base_repository:
            logger.info("Update remote origin", url=base_repository)
            origin.set_url(base_repository)

        # Always update the references for base repo
        logger.info("Fetch remote origin")
        origin.fetch()
    else:
        logger.info("Clone git repository", url=base_repository, path=path)
        repo = Repo.clone_from(base_repository, path)

    # Fetch head repository as a remote on top of base
    try:
        head = repo.remotes[head_slug]

        # Make sure head matches the url
        if head.url != head_repository:
            head.set_url(head_repository)

    except IndexError:
        # Setup new remote
        head = repo.create_remote(head_slug, head_repository)

    # Always fetch, as creating a remote does not fetch automatically
    logger.info("Fetch remote head", url=head.url)
    head.fetch()

    # Detach head to specified revision
    logger.info("Checkout to head", revision=revision)
    repo.head.reference = repo.commit(revision)

    return repo


class GitRepository(BaseRepository):
    """
    A Git repository with credentials to push a patch stack to a remote
    (e.g. a GitHub "try" repository).

    Notable differences from the Mercurial implementation:
    - the base revision is already a Git hash, so there is no Lando ``git2hg`` lookup;
    - pushes are authenticated over HTTPS with a short-lived GitHub App
      installation token generated at push time.
    """

    DEFAULT_REVISION = "HEAD"

    def __init__(self, config, cache_root):
        super().__init__(config, cache_root)

        # Branch pushed to the remote try repository
        self.head_branch = config.get("head_branch", "code-review")

        # GitHub App credentials used to generate short-lived push tokens
        self.github_app_id = config.get("github_app_id")
        self.github_app_privkey = config.get("github_app_privkey")
        self._github_token = None

    @property
    def repo(self):
        """Lazily open the local Git repository."""
        if self._repo is None:
            logger.info(f"Git open {self.dir}")
            self._repo = Repo(self.dir)
        return self._repo

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

    def authenticated_url(self, url):
        """Inject an installation token in an HTTPS GitHub url.

        Other urls (e.g. local paths in the test suite) are returned unchanged.
        """
        parts = urlparse(url)
        if parts.scheme not in ("http", "https"):
            return url
        return f"{parts.scheme}://git:{self.github_token()}@{parts.netloc}{parts.path}"

    def clone(self):
        # Read operations use the plain url: the repositories are public, only
        # pushes need authentication
        logger.info("Checking out git repository", repo=self.url, dir=self.dir)
        if os.path.isdir(os.path.join(self.dir, ".git")):
            self._repo = Repo(self.dir)
            self.repo.remotes.origin.fetch()
        else:
            self._repo = Repo.clone_from(self.url, self.dir)
        logger.info("Full checkout finished")

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

    def checkout_base(self, base):
        """Move the working tree to the base revision.

        HEAD is detached so the patches committed on top stay throwaway drafts
        and never advance a branch; clean() then discards them by returning to
        the base.
        """
        logger.info(f"Updating repo to revision {base}")
        self.repo.git.checkout(base, force=True, detach=True)

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

    def apply_patch(self, patch, message, commit):
        """Apply a single unified diff to the index and commit it."""
        name, email = self.get_author(commit)

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

    def commit_try_task_config(self, path, message):
        """Commit the try_task_config.json file as the bot"""
        self.repo.git.add(path)
        env = {
            "GIT_AUTHOR_NAME": DEFAULT_AUTHOR_NAME,
            "GIT_AUTHOR_EMAIL": DEFAULT_AUTHOR_EMAIL,
            "GIT_COMMITTER_NAME": DEFAULT_AUTHOR_NAME,
            "GIT_COMMITTER_EMAIL": DEFAULT_AUTHOR_EMAIL,
        }
        with self.repo.git.custom_environment(**env):
            self.repo.git.commit("--no-verify", "-m", message)

    def push_to_try(self):
        """Push the current HEAD to the remote try repository."""
        head = self.repo.head.commit
        logger.info("Pushing patches to try", rev=head.hexsha, branch=self.head_branch)
        self.repo.git.push(
            self.authenticated_url(self.try_url),
            f"HEAD:refs/heads/{self.head_branch}",
            force=True,
        )
        return head

    def revision_id(self, tip):
        """Extract the revision identifier from a push_to_try result"""
        return tip.hexsha

    def clean(self):
        """Reset the local checkout to a pristine state.

        Mirrors the Mercurial ``clean()`` (revert + strip outgoing drafts +
        pull): a reused clone can hold the patch commits and ``try_task_config``
        commit from a previous build, so we discard local changes, refresh from
        the remote and return to the base revision.
        """
        logger.info("Cleaning git checkout")

        # Discard uncommitted changes and untracked/ignored files
        self.repo.git.reset("--hard")
        self.repo.git.clean("-fxd")

        # Refresh from the remote when one is configured (mirrors hg pull)
        if any(remote.name == "origin" for remote in self.repo.remotes):
            self.repo.remotes.origin.fetch()

        # Return to the pristine base, dropping any previously applied commits.
        # Prefer the remote-tracking base so we also pick up upstream updates.
        upstream = f"origin/{self.default_revision}"
        if self.has_revision(upstream):
            target = upstream
        elif self.default_revision != "HEAD":
            target = self.default_revision
        else:
            # A bare HEAD cannot identify a pristine base once patches have
            # been committed on top of it
            raise Exception(
                "Cannot determine the base to reset to: configure default_revision "
                "or make sure the repository has an origin remote"
            )
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
