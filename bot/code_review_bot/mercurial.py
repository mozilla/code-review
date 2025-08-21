# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import atexit
import fcntl
import io
import json
import os
import tempfile
import time
from datetime import datetime

import hglib
import requests
import rs_parsepatch
import structlog
from libmozdata.phabricator import PhabricatorPatch
from libmozevent.phabricator import PhabricatorBuild
from libmozevent.utils import batch_checkout

from code_review_bot.config import settings

logger = structlog.get_logger(__name__)

TREEHERDER_URL = "https://treeherder.mozilla.org/#/jobs?repo={}&revision={}"
DEFAULT_AUTHOR = "code review bot <release-mgmt-analysis@mozilla.com>"
# On build failure, check try status until available every 5 minutes and up to 24h
TRY_STATUS_URL = "https://treestatus.prod.lando.prod.cloudops.mozgcp.net/trees/try"
TRY_STATUS_DELAY = 5 * 60
TRY_STATUS_MAX_WAIT = 24 * 60 * 60
# Number of allowed retries on an unexpected push fail
MAX_PUSH_RETRIES = 4
# Wait successive exponential delays: 6sec, 36sec, 3.6min, 21.6min
PUSH_RETRY_EXPONENTIAL_DELAY = 6

# External services to manage hash reference related to Git repositories
GIT_TO_HG = "https://lando.moz.tools/api/git2hg/firefox/{}"
FIREFOX_GITHUB_COMMIT_URL = (
    "https://api.github.com/repos/mozilla-firefox/firefox/commits/{}"
)

logger = structlog.get_logger(__name__)


class RetryNeeded(Exception):
    """
    Raised when retrying a mercurial build is needed
    """


def hg_run(cmd):
    """
    Run a mercurial command without an hglib instance
    Useful for initial custom clones
    Redirects stdout & stderr to python's logger

    This code has been copied from the libmozevent library
    https://github.com/mozilla/libmozevent/blob/fd0b3689c50c3d14ac82302b31115d0046c6e7c8/libmozevent/utils.py#L77
    """

    def _log_process(output, name):
        # Read and display every line
        out = output.read()
        if out is None:
            return
        text = filter(None, out.decode("utf-8").splitlines())
        for line in text:
            logger.info(f"{name}: {line}")

    # Start process
    main_cmd = cmd[0]
    proc = hglib.util.popen([hglib.HGPATH] + cmd)

    # Set process outputs as non blocking
    for output in (proc.stdout, proc.stderr):
        fcntl.fcntl(
            output.fileno(),
            fcntl.F_SETFL,
            fcntl.fcntl(output, fcntl.F_GETFL) | os.O_NONBLOCK,
        )

    while proc.poll() is None:
        _log_process(proc.stdout, main_cmd)
        _log_process(proc.stderr, f"{main_cmd} (err)")
        time.sleep(2)

    out, err = proc.communicate()
    if proc.returncode != 0:
        logger.error(f"Mercurial {main_cmd} failure", out=out, err=err, exc_info=True)
        raise hglib.error.CommandError(cmd, proc.returncode, out, err)

    return out


def robust_checkout(
    repo_url,
    checkout_dir,
    sharebase_dir,
    revision=None,
    branch=None,
    repo_upstream_url=None,
):
    if not ((revision is not None) ^ (branch is not None)):
        raise Exception("Set revision XOR branch")

    cmd = hglib.util.cmdbuilder(
        "robustcheckout",
        repo_url,
        checkout_dir,
        purge=True,
        sharebase=sharebase_dir,
        revision=revision,
        branch=branch,
        upstream=repo_upstream_url,
    )
    hg_run(cmd)


class Repository:
    """
    A Mercurial repository with its try server credentials
    """

    def __init__(self, config, cache_root):
        assert isinstance(config, dict)
        self.name = config["name"]
        self.url = config["url"]
        self.dir = os.path.join(cache_root, config["name"])
        self.share_base_dir = os.path.join(cache_root, f"{config['name']}-shared")
        self.checkout_mode = config.get("checkout", "batch")
        self.batch_size = config.get("batch_size", 10000)
        self.try_url = config["try_url"]
        self.try_name = config.get("try_name", "try")
        self.default_revision = config.get("default_revision", "tip")

        # Apply patches to the latest revision when `True`.
        self.use_latest_revision = config.get("use_latest_revision", False)

        # Crash when configuration requests try syntax
        if config.get("try_mode") == "syntax":
            raise Exception("Try syntax mode is deprecated")

        self._repo = None

        # Write ssh key from secret
        _, self.ssh_key_path = tempfile.mkstemp(suffix=".key")
        with open(self.ssh_key_path, "w") as f:
            f.write(config["ssh_key"])

        # Build ssh conf
        conf = {
            "StrictHostKeyChecking": "no",
            "User": config["ssh_user"],
            "IdentityFile": self.ssh_key_path,
        }
        self.ssh_conf = "ssh {}".format(
            " ".join(f'-o {k}="{v}"' for k, v in conf.items())
        ).encode("utf-8")

        # Remove key when finished
        atexit.register(self.end_of_life)

    def __str__(self):
        return self.name

    def end_of_life(self):
        os.unlink(self.ssh_key_path)
        logger.info("Removed ssh key")

    def clone(self):
        logger.info("Checking out tip", repo=self.url, mode=self.checkout_mode)
        if self.checkout_mode == "batch":
            batch_checkout(self.url, self.dir, b"tip", self.batch_size)
        elif self.checkout_mode == "robust":
            robust_checkout(self.url, self.dir, self.share_base_dir, branch=b"tip")
        else:
            hglib.clone(self.url, self.dir)
        logger.info("Full checkout finished")

        # Setup repo in main process
        self.repo.setcbout(lambda msg: logger.info("Mercurial", stdout=msg))
        self.repo.setcberr(lambda msg: logger.info("Mercurial", stderr=msg))

    @property
    def repo(self):
        """
        Get the repo instance, in case it's None re-open it
        """
        if self._repo is None or self._repo.server is None:
            logger.info(f"Mercurial open {self.dir}")
            self._repo = hglib.open(self.dir)

        return self._repo

    def get_mercurial_base_hash(self, revision):
        """A revision may reference to a Git commit hash instead of Mercurial one.
        The revision can either be a 40 characters full hash or its first 12 characters (short hash).
        It is the case for the base revision of the stack. Github's API helps to retrieve the full
        revision in case it is known.
        A Lando API enables to "convert" the Git hash to a Mercurial hash that can
        be found in the local repository.
        """
        if len(revision) == 40:
            complete_hash = revision
        elif len(revision) < 40:
            logger.info(
                f"Base revision is {len(revision)} characters length. "
                "Trying to retrieve complete hash from https://github.com/mozilla-firefox/firefox."
            )
            headers = {}
            if not settings.github_api_token:
                logger.warning(
                    "Performing Github API request has rate limitation when not authenticated. "
                    "Hint: Set the GITHUB_API_TOKEN environment variable."
                )
            else:
                headers["Authorization"] = f"Bearer {settings.github_api_token}"
            response = requests.get(
                FIREFOX_GITHUB_COMMIT_URL.format(revision),
                headers=headers,
            )
            if not response.ok:
                logger.warning(
                    f"Could not retrieve the complete hash: {response=}. "
                    "The default revision will be used instead."
                )
                return self.default_revision
            complete_hash = response.json()["sha"]
        else:
            logger.error(
                f"Revision must be a complete hash (40 chars) or short hash (<40 chars) (got '{revision}')"
            )
            raise ValueError(revision)

        response = requests.get(GIT_TO_HG.format(complete_hash))
        if not response.ok or not (hg_hash := response.json().get("hg_hash")):
            logger.warning(
                f"Could not convert Git hash to Mercurial hash from Lando: {response=}. "
                "The default revision will be used instead."
            )
            return self.default_revision
        return hg_hash

    def has_revision(self, revision):
        """
        Check if a revision is directly available on this Mercurial repo
        """
        if not revision:
            return False
        try:
            self.repo.identify(revision)
            return True
        except hglib.error.CommandError:
            return False

    def get_base_identifier(self, needed_stack: list[PhabricatorPatch]) -> str:
        """Return the base identifier to apply patches against."""
        if self.use_latest_revision:
            # Use `tip` when `use_latest_revision` is `True`.
            return "tip"

        # Otherwise use the base/parent revision of first revision in the stack.
        base_rev_hash = needed_stack[0].base_revision
        if self.has_revision(base_rev_hash):
            return base_rev_hash
        else:
            # Base revision may reference a Git hash on new repositories
            return self.get_mercurial_base_hash(base_rev_hash)

    def apply_build(self, build):
        """
        Apply a stack of patches to mercurial repo
        and commit them one by one
        """
        assert isinstance(build, PhabricatorBuild)
        assert len(build.stack) > 0, "No patches to apply"
        assert all(map(lambda p: isinstance(p, PhabricatorPatch), build.stack))

        # Find the first unknown base revision
        needed_stack = []
        for patch in reversed(build.stack):
            needed_stack.insert(0, patch)

            # Skip already merged patches
            if patch.merged:
                logger.info(
                    f"Skip applying patch {patch.id} as it's already been merged upstream"
                )
                continue

            # Stop as soon as a base revision is available
            if self.has_revision(patch.base_revision):
                logger.info(f"Stopping at revision {patch.base_revision}")
                break

        if not needed_stack:
            logger.info("All the patches are already applied")
            return

        hg_base = self.get_base_identifier(needed_stack)

        # When base revision is missing, update to default revision
        build.base_revision = hg_base
        build.missing_base_revision = not self.has_revision(hg_base)
        if build.missing_base_revision:
            logger.warning(
                "Missing base revision from Phabricator",
                revision=hg_base,
                fallback=self.default_revision,
            )
            hg_base = self.default_revision

        # Store the actual base revision we used
        build.actual_base_revision = hg_base

        # Update the repo to base revision
        try:
            logger.info(f"Updating repo to revision {hg_base}")
            self.repo.update(rev=hg_base, clean=True)

            # See if the repo is clean
            repo_status = self.repo.status(
                modified=True, added=True, removed=True, deleted=True
            )
            if len(repo_status) != 0:
                logger.warn(
                    "Repo is dirty!",
                    revision=hg_base,
                    repo=self.name,
                    repo_status=repo_status,
                )

        except hglib.error.CommandError:
            raise Exception(f"Failed to update to revision {hg_base}")

        # In this case revision is `hg_base`
        logger.info("Updated repo", revision=hg_base, repo=self.name)

        def get_author(commit):
            """Helper to build a mercurial author from Phabricator data"""
            author = commit.get("author")
            if author is None:
                return DEFAULT_AUTHOR
            if author["name"] and author["email"]:
                # Build clean version without quotes
                return f"{author['name']} <{author['email']}>"
            return author["raw"]

        for patch in needed_stack:
            if patch.commits:
                # Use the first commit only
                commit = patch.commits[0]
                message = "{}\n".format(commit["message"])
                user = get_author(commit)
            else:
                # We should always have some commits here
                logger.warning("Missing commit on patch", id=patch.id)
                message = ""
                user = DEFAULT_AUTHOR
            message += f"Differential Diff: {patch.phid}"

            logger.info("Applying patch", phid=patch.phid, message=message)
            patches = io.BytesIO(patch.patch.encode("utf-8"))
            try:
                self.repo.import_(
                    patches=patches,
                    message=message.encode("utf-8"),
                    user=user.encode("utf-8"),
                    similarity=95,
                )
            except hglib.error.CommandError as e:
                logger.warning(
                    (
                        f"Mercurial command from hglib failed: {e}. "
                        "Retrying with --config ui.patch=patch."
                    ),
                    phid=patch.phid,
                    exc_info=True,
                )
                patches.seek(0)
                # Same method as repo.import_() but with the extra argument "--config ui.patch=patch".
                # https://repo.mercurial-scm.org/python-hglib/file/484b56ac4aec/hglib/client.py#l959
                hg_command = hglib.cmdbuilder(
                    b"import",
                    message=message.encode("utf-8"),
                    user=user.encode("utf-8"),
                    similarity=95,
                    config="ui.patch=patch",
                    *patches,
                )
                hg_run(hg_command)
            except Exception as e:
                logger.info(
                    f"Failed to apply patch: {e}",
                    phid=patch.phid,
                    exc_info=True,
                )
                raise

    def add_try_commit(self, build):
        """
        Build and commit the file configuring try
        with try_task_config.json and the code-review workflow parameters in JSON
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
        self.repo.add(path.encode("utf-8"))
        self.repo.commit(message=message, user=DEFAULT_AUTHOR)

    def push_to_try(self):
        """
        Push the current tip on remote try repository
        """
        tip = self.repo.tip()
        logger.info("Pushing patches to try", rev=tip.node)
        self.repo.push(
            dest=self.try_url.encode("utf-8"),
            rev=tip.node,
            ssh=self.ssh_conf,
            force=True,
        )
        return tip

    def clean(self):
        """
        Steps to clean the mercurial repo
        """
        logger.info("Remove uncommitted changes")
        self.repo.revert(self.dir.encode("utf-8"), all=True)

        logger.info("Remove all mercurial drafts")
        try:
            cmd = hglib.util.cmdbuilder(
                b"strip", rev=b"roots(outgoing())", force=True, backup=False
            )
            self.repo.rawcommand(cmd)
        except hglib.error.CommandError as e:
            if b"abort: empty revision set" not in e.err:
                raise

        logger.info("Pull updates from remote repo")
        self.repo.pull()


class MercurialWorker:
    """
    Mercurial worker maintaining several local clones
    """

    ELIGIBLE_RETRY_ERRORS = [
        error.lower()
        for error in [
            "push failed on remote",
            "stream ended unexpectedly",
            "error: EOF occurred in violation of protocol",
        ]
    ]

    def __init__(
        self,
        skippable_files=[],
    ):
        self.skippable_files = skippable_files

    def run(self, repository, build):
        """
        Apply the stack of patches from the build, handling retries
        in case of try server errors
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
                    logger.warn("Mercurial error on diff", error=error_log, build=build)
                    return (
                        "fail:mercurial",
                        build,
                        {"message": error_log, "duration": time.time() - start},
                    )

                # Ensure try is opened
                self.wait_try_available()

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

    def wait_try_available(self):
        """
        Wait until try status is "open"
        On each failure, wait TRY_STATUS_DELAY before retrying up to TRY_STATUS_MAX_WAIT
        """

        def get_status():
            try:
                resp = requests.get(TRY_STATUS_URL)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.warning(f"An error occurred retrieving try status: {e}")
            else:
                return data.get("result", {}).get("status")

        start = datetime.utcnow()
        while status := get_status() != "open":
            if (datetime.utcnow() - start).seconds >= TRY_STATUS_MAX_WAIT:
                logger.error(
                    f"Try tree status still closed after {TRY_STATUS_MAX_WAIT} seconds, skipping",
                    exc_info=True,
                )
                break
            logger.warning(
                f"Try tree is not actually open (status: {status}), waiting {TRY_STATUS_DELAY} seconds before retrying"
            )
            time.sleep(TRY_STATUS_DELAY)

    def is_eligible_for_retry(self, error):
        """
        Given a Mercurial error message, if it's an error likely due to a
        temporary connection problem, consider it as eligible for retry.
        """
        error = error.lower()
        return any(
            eligible_message in error for eligible_message in self.ELIGIBLE_RETRY_ERRORS
        )

    def handle_build(self, repository, build):
        """
        Try to load and apply a diff on local clone
        If successful, push to try and send a treeherder link
        In case of an unexpected push failure, retry up to MAX_PUSH_RETRIES
        times by putting the build task back in the queue

        If the build fail, send a unit result with a warning message
        """
        assert isinstance(repository, Repository)
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
            uri = TREEHERDER_URL.format(repository.try_name, tip.node.decode("utf-8"))
        except hglib.error.CommandError as e:
            # Format nicely the error log
            error_log = e.err
            if isinstance(error_log, bytes):
                error_log = error_log.decode("utf-8")

            if self.is_eligible_for_retry(error_log):
                raise RetryNeeded

            logger.warn(
                "Mercurial error on diff", error=error_log, args=e.args, build=build
            )
            return (
                "fail:mercurial",
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
            {"treeherder_url": uri, "revision": tip.node.decode("utf-8")},
        )
