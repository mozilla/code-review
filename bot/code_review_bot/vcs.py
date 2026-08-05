# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os
import time

import rs_parsepatch
import structlog
from libmozdata.phabricator import PhabricatorPatch

from code_review_bot.sources.phabricator import PhabricatorBuild

logger = structlog.get_logger(__name__)

TREEHERDER_URL = "https://treeherder.mozilla.org/#/jobs?repo={}&revision={}"

# Number of allowed retries on an unexpected push fail
MAX_PUSH_RETRIES = 4
# Wait successive exponential delays: 6sec, 36sec, 3.6min, 21.6min
PUSH_RETRY_EXPONENTIAL_DELAY = 6


class RetryNeeded(Exception):
    """
    Raised when retrying a build is needed
    """


class BaseRepository:
    """
    A repository with its try server credentials, independent of the
    version control system.

    Subclasses provide the VCS specific operations: cloning, revision
    lookups, applying a patch as a commit and pushing to the try server.
    """

    # Revision to apply patches on when the base revision is unknown
    DEFAULT_REVISION = None

    def __init__(self, config, cache_root):
        assert isinstance(config, dict)
        self.name = config["name"]
        self.url = config["url"]
        self.dir = os.path.join(cache_root, config["name"])
        self.try_url = config["try_url"]
        self.try_name = config.get("try_name", "try")
        self.default_revision = config.get("default_revision", self.DEFAULT_REVISION)

        # Apply patches to the latest revision when `True`.
        self.use_latest_revision = config.get("use_latest_revision", False)

        self._repo = None

    def __str__(self):
        return self.name

    def clone(self):
        """Clone the repository in the local cache directory, or refresh an
        existing clone, so that a stack of patches can be applied on it"""
        raise NotImplementedError

    def has_revision(self, revision):
        """Check if a revision is directly available in the local repository"""
        raise NotImplementedError

    def get_base_identifier(self, needed_stack: list[PhabricatorPatch]) -> str:
        """Return the revision identifier the stack of patches must be
        applied against"""
        raise NotImplementedError

    def checkout_base(self, base):
        """Update the local checkout to the base revision"""
        raise NotImplementedError

    def apply_patch(self, patch: PhabricatorPatch, message, commit):
        """Apply a single patch on the local checkout and commit it,
        using the author from the Phabricator commit data"""
        raise NotImplementedError

    def commit_try_task_config(self, path, message):
        """Commit the try_task_config.json file as the bot"""
        raise NotImplementedError

    def push_to_try(self):
        """Push the locally applied stack to the remote try repository and
        return the pushed tip, in the format accepted by revision_id()"""
        raise NotImplementedError

    def revision_id(self, tip):
        """Extract the revision identifier from a push_to_try result"""
        raise NotImplementedError

    def clean(self):
        """Restore the local repository to a pristine state, dropping the
        commits applied by a previous build and pulling remote updates"""
        raise NotImplementedError

    def apply_build(self, build):
        """
        Apply a stack of patches to the local repository
        and commit them one by one
        """
        assert isinstance(build, PhabricatorBuild)
        assert len(build.stack) > 0, "No patches to apply"
        assert all(map(lambda p: isinstance(p, PhabricatorPatch), build.stack))

        # Find the first unknown base revision
        needed_stack = []
        for patch in reversed(build.stack):
            # Skip already merged patches
            if patch.merged:
                logger.info(
                    f"Skip applying patch {patch.id} as it's already been merged upstream"
                )
                continue

            # Add the patch into the stack only if not already merged !
            needed_stack.insert(0, patch)

            # Stop as soon as a base revision is available
            if self.has_revision(patch.base_revision):
                logger.info(f"Stopping at revision {patch.base_revision}")
                break

        if not needed_stack:
            logger.info("All the patches are already applied")
            return

        base = self.get_base_identifier(needed_stack)

        # When base revision is missing, update to default revision
        build.base_revision = base
        build.missing_base_revision = not self.has_revision(base)
        if build.missing_base_revision:
            logger.warning(
                "Missing base revision from Phabricator",
                revision=base,
                fallback=self.default_revision,
            )
            base = self.default_revision

        # Store the actual base revision we used
        build.actual_base_revision = base

        self.checkout_base(base)

        for patch in needed_stack:
            if patch.commits:
                # Use the first commit only
                commit = patch.commits[0]
                message = "{}\n".format(commit["message"])
            else:
                # We should always have some commits here
                logger.warning("Missing commit on patch", id=patch.id)
                commit = None
                message = ""
            message += f"Differential Diff: {patch.phid}"

            logger.info("Applying patch", phid=patch.phid, message=message)
            self.apply_patch(patch, message, commit)

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
        self.commit_try_task_config(path, message)


class BaseWorker:
    """
    Worker maintaining several local clones and applying builds on them,
    independent of the version control system.
    """

    # Exception raised by the VCS layer on a failing command
    VCS_ERROR = ()
    # Human readable VCS name, used in logs
    VCS_NAME = None
    # Worker output mode on a VCS failure
    FAILURE_MODE = None
    # Repository class handled by this worker
    REPOSITORY_CLASS = BaseRepository
    # Lowercase error messages elligible for a push retry
    ELIGIBLE_RETRY_ERRORS = []

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
                    logger.warn(
                        f"{self.VCS_NAME} error on diff", error=error_log, build=build
                    )
                    return (
                        self.FAILURE_MODE,
                        build,
                        {"message": error_log, "duration": time.time() - start},
                    )

                # Ensure the remote is available
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
        Hook called before retrying a failed push, doing nothing by default
        """

    def is_eligible_for_retry(self, error):
        """
        Given a VCS error message, if it's an error likely due to a
        temporary connection problem, consider it as eligible for retry.
        """
        error = error.lower()
        return any(
            eligible_message in error for eligible_message in self.ELIGIBLE_RETRY_ERRORS
        )

    def format_error(self, error):
        """Extract a readable error log from a VCS exception"""
        raise NotImplementedError

    def handle_build(self, repository, build):
        """
        Try to load and apply a diff on local clone
        If successful, push to try and send a treeherder link
        In case of an unexpected push failure, retry up to MAX_PUSH_RETRIES
        times by putting the build task back in the queue

        If the build fail, send a unit result with a warning message
        """
        assert isinstance(repository, self.REPOSITORY_CLASS)
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
            uri = TREEHERDER_URL.format(
                repository.try_name, repository.revision_id(tip)
            )
        except self.VCS_ERROR as e:
            error_log = self.format_error(e)

            if self.is_eligible_for_retry(error_log):
                raise RetryNeeded

            logger.warn(
                f"{self.VCS_NAME} error on diff",
                error=error_log,
                args=e.args,
                build=build,
            )
            return (
                self.FAILURE_MODE,
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
            {"treeherder_url": uri, "revision": repository.revision_id(tip)},
        )
