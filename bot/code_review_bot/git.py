import atexit
import json
import os
import re
import tempfile
import time
from urllib.parse import urlparse

import rs_parsepatch
import structlog
from git import Repo
from git.exc import GitCommandError
from libmozdata.phabricator import PhabricatorPatch

from code_review_bot.sources.phabricator import PhabricatorBuild

logger = structlog.getLogger(__name__)

# Treeherder job URL for a pushed revision. The repository name (first slot) is
# the Treeherder repo, refined for the Git try repository in a later change.
TREEHERDER_URL = "https://treeherder.mozilla.org/#/jobs?repo={}&revision={}"

# Number of allowed retries on an unexpected push failure, and the base of the
# exponential backoff between them (6s, 36s, 3.6min, 21.6min). Mirrors the
# Mercurial worker, minus the treestatus wait (there is no Git "try" tree).
MAX_PUSH_RETRIES = 4
PUSH_RETRY_EXPONENTIAL_DELAY = 6

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


class RetryNeeded(Exception):
    """
    Raised when retrying a Git build is needed
    """


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


class GitRepository:
    """
    A Git repository with credentials to push a patch stack to a remote
    (e.g. a GitHub "try" repository).

    Mirrors the interface of the Mercurial ``Repository``
    (``code_review_bot.mercurial.Repository``) so the same workflow can apply a
    Phabricator patch stack and push it, but targeting Git instead of Mercurial.

    Notable differences from the Mercurial implementation:
    - the base revision is already a Git hash, so there is no Lando ``git2hg`` lookup;
    - authentication uses an SSH deploy key passed through ``GIT_SSH_COMMAND``.
    """

    def __init__(self, config, cache_root):
        assert isinstance(config, dict)
        self.name = config["name"]
        self.url = config["url"]
        self.dir = os.path.join(cache_root, config["name"])
        self.try_url = config["try_url"]
        self.try_name = config.get("try_name", "try")

        # Revision/branch to apply patches on when the base is unknown locally
        self.default_revision = config.get("default_revision", "HEAD")

        # Branch pushed to the remote try repository.
        # TODO: the per-build ref model is still an open question (see plan Q2).
        self.head_branch = config.get("head_branch", "code-review")

        # Apply patches on the latest revision when True
        self.use_latest_revision = config.get("use_latest_revision", False)

        self._repo = None

        # Write the SSH (deploy) key from the configuration to a temporary file
        _, self.ssh_key_path = tempfile.mkstemp(suffix=".key")
        with open(self.ssh_key_path, "w") as f:
            f.write(config["ssh_key"])
        os.chmod(self.ssh_key_path, 0o600)
        self.git_ssh_command = f"ssh -i {self.ssh_key_path} -o StrictHostKeyChecking=no"

        # Remove the key when finished
        atexit.register(self.end_of_life)

    def __str__(self):
        return self.name

    def end_of_life(self):
        if os.path.exists(self.ssh_key_path):
            os.unlink(self.ssh_key_path)
            logger.info("Removed ssh key")

    @property
    def repo(self):
        """Lazily open the local Git repository."""
        if self._repo is None:
            logger.info(f"Git open {self.dir}")
            self._repo = Repo(self.dir)
        return self._repo

    def clone(self):
        logger.info("Checking out git repository", repo=self.url, dir=self.dir)
        if os.path.isdir(os.path.join(self.dir, ".git")):
            self._repo = Repo(self.dir)
            with self.repo.git.custom_environment(GIT_SSH_COMMAND=self.git_ssh_command):
                self.repo.remotes.origin.fetch()
        else:
            self._repo = Repo.clone_from(
                self.url, self.dir, env={"GIT_SSH_COMMAND": self.git_ssh_command}
            )
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

        Unlike Mercurial, the base revision is already a Git hash, so there is no
        Lando ``git2hg`` conversion: when the base is not available locally we fall
        back to the default revision.
        """
        if self.use_latest_revision:
            return self.default_revision

        base_revision = needed_stack[0].base_revision
        if self.has_revision(base_revision):
            return base_revision

        logger.warning(
            "Base revision not available locally, using the default revision",
            revision=base_revision,
            default=self.default_revision,
        )
        return self.default_revision

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

    def commit_patch(self, patch_content, message, name, email):
        """Apply a single unified diff to the index and commit it."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".diff", delete=False
        ) as patch_file:
            patch_file.write(self.normalize_patch(patch_content))
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

    def apply_build(self, build):
        """Apply a stack of Phabricator patches as Git commits."""
        assert isinstance(build, PhabricatorBuild)
        assert len(build.stack) > 0, "No patches to apply"
        assert all(isinstance(p, PhabricatorPatch) for p in build.stack)

        # Find the first unknown base revision
        needed_stack = []
        for patch in reversed(build.stack):
            # Skip already merged patches
            if patch.merged:
                logger.info(
                    f"Skip applying patch {patch.id} as it's already been merged upstream"
                )
                continue

            # Add the patch into the stack only if not already merged
            needed_stack.insert(0, patch)

            # Stop as soon as a base revision is available
            if self.has_revision(patch.base_revision):
                logger.info(f"Stopping at revision {patch.base_revision}")
                break

        if not needed_stack:
            logger.info("All the patches are already applied")
            return

        git_base = self.get_base_identifier(needed_stack)

        # When base revision is missing, fall back to the default revision
        build.base_revision = git_base
        build.missing_base_revision = not self.has_revision(git_base)
        if build.missing_base_revision:
            logger.warning(
                "Missing base revision from Phabricator",
                revision=git_base,
                fallback=self.default_revision,
            )
            git_base = self.default_revision

        # Store the actual base revision we used
        build.actual_base_revision = git_base

        # Move the working tree to the base revision. Detach HEAD so the patches
        # we commit on top stay throwaway drafts and never advance a branch ref;
        # clean() can then discard them simply by returning to the base.
        logger.info(f"Updating repo to revision {git_base}")
        self.repo.git.checkout(git_base, force=True, detach=True)

        for patch in needed_stack:
            if patch.commits:
                # Use the first commit only
                commit = patch.commits[0]
                message = "{}\n".format(commit["message"])
                name, email = self.get_author(commit)
            else:
                # We should always have some commits here
                logger.warning("Missing commit on patch", id=patch.id)
                message = ""
                name, email = DEFAULT_AUTHOR_NAME, DEFAULT_AUTHOR_EMAIL
            message += f"Differential Diff: {patch.phid}"

            logger.info("Applying patch", phid=patch.phid, message=message)
            self.commit_patch(patch.patch, message, name, email)

    def add_try_commit(self, build):
        """
        Build and commit the file configuring try with try_task_config.json
        and the code-review workflow parameters in JSON
        """
        path = os.path.join(self.dir, "try_task_config.json")
        config = {
            "version": 2,
            "parameters": {
                "target_tasks_method": "codereview",
                "optimize_target_tasks": True,
                "phabricator_diff": build.target_phid,
            },
        }
        diff_phid = build.stack[-1].phid

        if build.revision_url:
            message = f"try_task_config for {build.revision_url}"
        else:
            message = "try_task_config for code-review"
        message += f"\nDifferential Diff: {diff_phid}"

        # Write content as json and commit it
        with open(path, "w") as f:
            json.dump(config, f, sort_keys=True, indent=4)

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
        """Push the current HEAD to the remote try repository over the deploy key."""
        head = self.repo.head.commit
        logger.info("Pushing patches to try", rev=head.hexsha, branch=self.head_branch)
        with self.repo.git.custom_environment(GIT_SSH_COMMAND=self.git_ssh_command):
            self.repo.git.push(
                self.try_url, f"HEAD:refs/heads/{self.head_branch}", force=True
            )
        return head

    def clean(self):
        """Reset the local checkout to a pristine state.

        Mirrors the Mercurial ``clean()`` (revert + strip outgoing drafts +
        pull): a reused clone can hold the patch commits and ``try_task_config``
        commit from a previous build, so we discard local changes, refresh from
        the remote and return to the base revision. Because ``apply_build``
        commits on a detached HEAD, returning to the base leaves those commits
        unreferenced instead of accumulating them on a branch.
        """
        logger.info("Cleaning git checkout")

        # Discard uncommitted changes and untracked/ignored files
        self.repo.git.reset("--hard")
        self.repo.git.clean("-fxd")

        # Refresh from the remote when one is configured (mirrors hg pull)
        if any(remote.name == "origin" for remote in self.repo.remotes):
            with self.repo.git.custom_environment(GIT_SSH_COMMAND=self.git_ssh_command):
                self.repo.remotes.origin.fetch()

        # Return to the pristine base, dropping any previously applied commits.
        # Prefer the remote-tracking base so we also pick up upstream updates.
        upstream = f"origin/{self.default_revision}"
        target = upstream if self.has_revision(upstream) else self.default_revision
        self.repo.git.checkout(self.default_revision, force=True)
        self.repo.git.reset("--hard", target)


class GitWorker:
    """
    Drive a GitRepository through a single build: clean, apply the patch stack,
    push to the remote try repository and return a Treeherder link.

    Mirrors ``code_review_bot.mercurial.MercurialWorker`` but for Git. The key
    difference is that there is no treestatus wait before retrying: Git has no
    "try" tree to gate on, so failed pushes are simply retried with backoff.
    """

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

    def __init__(self, skippable_files=[]):
        self.skippable_files = skippable_files

    def run(self, repository, build):
        """
        Apply the stack of patches from the build, retrying on remote push
        errors. Unlike the Mercurial worker, there is no treestatus wait.
        """
        while build.retries <= MAX_PUSH_RETRIES:
            start = time.time()

            if build.retries:
                logger.warning(
                    "Trying to apply build's diff after a remote push error "
                    f"[{build.retries}/{MAX_PUSH_RETRIES}]"
                )

            try:
                return self.handle_build(repository, build)
            except RetryNeeded:
                build.retries += 1

                if build.retries > MAX_PUSH_RETRIES:
                    error_log = "Max number of retries has been reached pushing the build to try repository"
                    logger.warn("Git error on diff", error=error_log, build=build)
                    return (
                        "fail:git",
                        build,
                        {"message": error_log, "duration": time.time() - start},
                    )

                # Wait an exponential time before retrying the build
                delay = PUSH_RETRY_EXPONENTIAL_DELAY**build.retries
                logger.info(
                    f"An error occurred pushing the build to try, retrying after {delay}s"
                )
                time.sleep(delay)

    def is_commit_skippable(self, build):
        def get_files_touched_in_diff(rawdiff):
            patched = []
            for parsed_diff in rs_parsepatch.get_diffs(rawdiff):
                # filename is sometimes of format 'test.txt  Tue Feb 05 17:23:40 2019 +0100'
                # fix after https://github.com/mozilla/rust-parsepatch/issues/61
                if "filename" in parsed_diff:
                    filename = parsed_diff["filename"].split(" ")[0]
                    patched.append(filename)
            return patched

        return any(
            patched_file in self.skippable_files
            for rev in build.stack
            for patched_file in get_files_touched_in_diff(rev.patch)
        )

    def is_eligible_for_retry(self, error):
        """
        Given a Git error message, if it's likely due to a temporary connection
        problem, consider it eligible for retry.
        """
        error = error.lower()
        return any(
            eligible_message in error for eligible_message in self.ELIGIBLE_RETRY_ERRORS
        )

    def handle_build(self, repository, build):
        """
        Apply the build's diff on the local clone; on success push to try and
        return a treeherder link. Unexpected push failures raise RetryNeeded so
        run() retries; other failures return a warning result.
        """
        assert isinstance(repository, GitRepository)
        start = time.time()

        try:
            # Start by cleaning the repo
            repository.clean()

            # First apply patches on local repo
            repository.apply_build(build)

            # Check Eligibility: some commits don't need to be pushed to try.
            if self.is_commit_skippable(build):
                logger.info("This patch series is ineligible for automated try push")
                return (
                    "fail:ineligible",
                    build,
                    {
                        "message": "Modified files match skippable internal configuration files",
                        "duration": time.time() - start,
                    },
                )

            # Configure the try task
            repository.add_try_commit(build)

            # Then push that stack on try
            tip = repository.push_to_try()
            logger.info("Diff has been pushed !")

            # Publish Treeherder link
            uri = TREEHERDER_URL.format(repository.try_name, tip.hexsha)
        except GitCommandError as e:
            error_log = e.stderr or str(e)

            if self.is_eligible_for_retry(error_log):
                raise RetryNeeded

            logger.warn("Git error on diff", error=error_log, args=e.args, build=build)
            return (
                "fail:git",
                build,
                {"message": error_log, "duration": time.time() - start},
            )

        except Exception as e:
            logger.warn("Failed to process diff", error=e, build=build)
            return (
                "fail:general",
                build,
                {"message": str(e), "duration": time.time() - start},
            )

        return (
            "success",
            build,
            {"treeherder_url": uri, "revision": tip.hexsha},
        )
