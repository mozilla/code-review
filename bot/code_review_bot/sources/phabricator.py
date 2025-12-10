# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import collections
import enum
import time
from datetime import datetime, timedelta

import structlog
from libmozdata.phabricator import PhabricatorAPI

logger = structlog.get_logger(__name__)


class PhabricatorBuildState(enum.Enum):
    Queued = 1
    Secured = 2
    Public = 3
    Expired = 4


class PhabricatorBuild:
    """
    A Phabricator buildable, triggered by HarborMaster
    """

    def __init__(self, request):
        self.diff_id = int(request.rel_url.query.get("diff", 0))
        self.repo_phid = request.rel_url.query.get("repo")
        self.revision_id = int(request.rel_url.query.get("revision", 0))
        self.target_phid = request.rel_url.query.get("target")
        self.state = PhabricatorBuildState.Queued
        # Incremented on an unexpected failure during build's push to try
        self.retries = 0

        if (
            not self.diff_id
            or not self.repo_phid
            or not self.revision_id
            or not self.target_phid
        ):
            raise Exception("Invalid webhook parameters")
        assert isinstance(self.revision_id, int), "Revision should be an integer"
        assert isinstance(self.target_phid, str), "Target should be a string"
        assert self.target_phid.startswith("PHID-HMBT-"), "Invalid target format"

        # Remote objects loaded by actions below
        self.revision = None
        self.revision_url = None
        self.reviewers = []
        self.diff = None
        self.stack = []
        self.base_revision = None
        self.missing_base_revision = False
        self.actual_base_revision = None

    def __str__(self):
        return f"Revision {self.revision_id} - {self.target_phid}"


class PhabricatorActions:
    """
    Common Phabricator actions shared across clients
    """

    def __init__(
        self, url, api_key, retries=5, sleep=10, build_expiry=timedelta(hours=24)
    ):
        self.api = PhabricatorAPI(url=url, api_key=api_key)

        # Phabricator secure revision retries configuration
        assert isinstance(retries, int)
        assert isinstance(sleep, int)
        self.max_retries = retries
        self.retries = collections.defaultdict(lambda: (retries, None))
        self.sleep = sleep
        self.build_expiry = build_expiry
        logger.info(
            "Will retry Phabricator secure revision queries",
            retries=retries,
            sleep=sleep,
            build_expiry=build_expiry,
        )

        # Load secure projects
        projects = self.api.search_projects(slugs=["secure-revision"])
        self.secure_projects = {p["phid"]: p["fields"]["name"] for p in projects}
        logger.info("Loaded secure projects", projects=self.secure_projects.values())

    def update_state(self, build):
        """
        Check the visibility of the revision, by retrying N times with an exponential backoff time
        This method is executed regularly by the client application to check on the status evolution
        as the BMO daemon can take several minutes to update the status
        """
        assert isinstance(build, PhabricatorBuild)

        # Only when queued
        if build.state != PhabricatorBuildState.Queued:
            return

        # Check this build has some retries left
        retries_left, last_try = self.retries[build.target_phid]
        if retries_left <= 0:
            return

        # Check this build has been awaited between tries
        exp_backoff = (2 ** (self.max_retries - retries_left)) * self.sleep
        now = time.time()
        if last_try is not None and now - last_try < exp_backoff:
            return

        # Now we can check if this revision is public
        retries_left -= 1
        self.retries[build.target_phid] = (retries_left, now)
        logger.info(
            "Checking visibility status", build=str(build), retries_left=retries_left
        )

        if self.is_visible(build):
            build.state = PhabricatorBuildState.Public
            build.revision_url = self.build_revision_url(build)
            logger.info("Revision is public", build=str(build))

            # Check if the build has not expired
            if self.is_expired_build(build):
                build.state = PhabricatorBuildState.Expired
                logger.info("Revision has expired", build=str(build))

        elif retries_left <= 0:
            # Mark as secured when no retries are left
            build.state = PhabricatorBuildState.Secured
            logger.info("Revision is marked as secure", build=str(build))

        else:
            # Enqueue back to retry later
            build.state = PhabricatorBuildState.Queued

    def is_visible(self, build):
        """
        Check the visibility of the revision by loading its details
        """
        assert isinstance(build, PhabricatorBuild)
        assert build.state == PhabricatorBuildState.Queued
        try:
            # Load revision with projects
            build.revision = self.api.load_revision(
                rev_id=build.revision_id,
                attachments={"projects": True, "reviewers": True},
            )
            if not build.revision:
                raise Exception("Not found")

            # Check against secure projects
            projects = set(build.revision["attachments"]["projects"]["projectPHIDs"])
            if projects.intersection(self.secure_projects):
                raise Exception("Secure revision")
        except Exception as e:
            logger.info("Revision not accessible", build=str(build), error=str(e))
            return False

        return True

    def load_patches_stack(self, build):
        """
        Load a stack of patches for a public Phabricator build
        without hitting a local mercurial repository
        """
        build.stack = self.api.load_patches_stack(build.diff_id, build.diff)

    def load_reviewers(self, build):
        """
        Load details for reviewers found on a build
        """
        assert isinstance(build, PhabricatorBuild)
        assert build.state == PhabricatorBuildState.Public
        assert build.revision is not None

        def load_user(phid):
            if phid.startswith("PHID-USER"):
                return self.api.load_user(user_phid=phid)
            elif phid.startswith("PHID-PROJ"):
                logger.info(f"Skipping group reviewer {phid}")
            else:
                raise Exception(f"Unsupported reviewer {phid}")

        reviewers = build.revision["attachments"]["reviewers"]["reviewers"]
        build.reviewers = list(
            filter(
                None, [load_user(reviewer["reviewerPHID"]) for reviewer in reviewers]
            )
        )

    def build_revision_url(self, build):
        """
        Build a Phabricator frontend url for a build's revision
        """
        return f"https://{self.api.hostname}/D{build.revision_id}"

    def is_expired_build(self, build):
        """
        Check if a build has expired, using its Phabricator diff information
        Returns True when the build has expired and should not be processed
        """
        assert isinstance(build, PhabricatorBuild)

        # We need Phabricator diff details to get the date
        if build.diff is None:
            try:
                diffs = self.api.search_diffs(diff_id=build.diff_id)
                if not diffs:
                    raise Exception(f"Diff {build.diff_id} not found on Phabricator")
                build.diff = diffs[0]
            except Exception as e:
                logger.warn("Failed to load diff", build=str(build), err=str(e))
                return False

        # Then we can check on the expiry date
        date_created = build.diff.get("dateCreated")
        if not date_created:
            logger.warn("No creation date found", build=str(build))
            return False

        logger.info("Found diff creation date", build=str(build), created=date_created)

        return datetime.now() - datetime.fromtimestamp(date_created) > self.build_expiry
