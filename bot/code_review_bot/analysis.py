import structlog
from libmozdata.phabricator import BuildState, UnitResult, UnitResultState
from libmozevent.phabricator import PhabricatorBuild, PhabricatorBuildState

logger = structlog.get_logger(__name__)


LANDO_WARNING_MESSAGE = "Static analysis and linting are still in progress."
LANDO_FAILURE_MESSAGE = (
    "Static analysis and linting did not run due to a generic failure."
)
LANDO_FAILURE_HG_MESSAGE = (
    "Static analysis and linting did not run due to failure in applying the patch."
)


class RevisionBuild(PhabricatorBuild):
    """
    Convert the bot revision into a libmozevent compatible build
    """

    def __init__(self, revision):
        # State should be updated to Public
        self.state = PhabricatorBuildState.Queued

        # Incremented on an unexpected failure during build's push to try
        self.retries = 0

        # Revision used by Phabricator updates
        # Direct output of Phabricator API (not the object passed here)
        self.revision_id = revision.phabricator_id
        self.revision_url = None
        self.revision = None

        # Needed to update Phabricator Harbormaster
        self.target_phid = revision.build_target_phid

        # Needed to load stack of patches
        self.diff = revision.diff
        self.diff_id = revision.diff_id
        self.stack = None

        # Needed to apply patch and communicate on Phabricator
        self.base_revision = None
        self.actual_base_revision = None
        self.missing_base_revision = False

    def __str__(self):
        return f"Phabricator Revision {self.revision_id} - Diff {self.diff_id}"

    def __repr__(self):
        return str(self)

    def load_patches_stack(self, phabricator_api):
        """
        Load the stack of patches from Phabricator API
        """
        self.stack = phabricator_api.load_patches_stack(self.diff_id, self.diff)
        return self.stack


def publish_analysis_phabricator(payload, phabricator_api):
    mode, build, extras = payload

    if build.target_phid is None:
        logger.warning(
            "No Phabricator build target, so no publication", mode=mode, build=build
        )
        return

    logger.info("Publishing a Phabricator build update", mode=mode, build=build)

    if mode == "fail:general":
        failure = UnitResult(
            namespace="code-review",
            name="general",
            result=UnitResultState.Broken,
            details="WARNING: An error occurred in the code review bot.\n\n```{}```".format(
                extras["message"]
            ),
            format="remarkup",
            duration=extras.get("duration", 0),
        )
        phabricator_api.update_build_target(
            build.target_phid, BuildState.Fail, unit=[failure]
        )

    elif mode == "fail:mercurial":
        extra_content = ""
        if build.missing_base_revision:
            extra_content = f" because the parent revision ({build.base_revision}) does not exist on mozilla-unified. If possible, you should publish that revision"

        failure = UnitResult(
            namespace="code-review",
            name="mercurial",
            result=UnitResultState.Fail,
            details="WARNING: The code review bot failed to apply your patch{}.\n\n```{}```".format(
                extra_content, extras["message"]
            ),
            format="remarkup",
            duration=extras.get("duration", 0),
        )
        phabricator_api.update_build_target(
            build.target_phid, BuildState.Fail, unit=[failure]
        )

    elif mode == "test_result":
        result = UnitResult(
            namespace="code-review",
            name=extras["name"],
            result=extras["result"],
            details=extras["details"],
        )
        phabricator_api.update_build_target(
            build.target_phid, BuildState.Work, unit=[result]
        )

    elif mode == "success":
        if build.missing_base_revision:
            # Publish a warning message on Phabricator in the Unit Tests section,
            # as done for other warnings/errors from the bot, since this section
            # is centered and at the top of the page.
            warning = UnitResult(
                namespace="code-review",
                name="mercurial",
                result=UnitResultState.Unsound,
                details=f"WARNING: The base revision of your patch is not available in the current repository.\nYour patch has been rebased on central (revision {build.actual_base_revision}): issues may be positioned at the wrong lines.",
            )
            phabricator_api.update_build_target(
                build.target_phid, BuildState.Work, unit=[warning]
            )
            logger.debug(
                "Missing base revision on PhabricatorBuild, adding a warning to Unit Tests section on Phabricator"
            )

        phabricator_api.create_harbormaster_uri(
            build.target_phid,
            "treeherder",
            "CI (Treeherder) Jobs",
            extras["treeherder_url"],
        )

    elif mode == "work":
        phabricator_api.update_build_target(build.target_phid, BuildState.Work)
        logger.info("Published public build as working", build=str(build))

    else:
        logger.warning("Unsupported publication", mode=mode, build=build)


def publish_analysis_lando(payload, lando_warnings):
    """
    Publish result of patch application and push to try on Lando
    """
    mode, build, extras = payload
    assert isinstance(build, RevisionBuild), "Not a RevisionBuild"
    logger.debug("Publishing a Lando build update", mode=mode, build=str(build))

    if mode == "fail:general":
        # Send general failure message to Lando
        logger.info(
            "Publishing code review failure.",
            revision=build.revision["id"],
            diff=build.diff_id,
        )
        try:
            lando_warnings.add_warning(
                LANDO_FAILURE_MESSAGE, build.revision["id"], build.diff_id
            )
        except Exception as ex:
            logger.error(str(ex), exc_info=True)

    elif mode == "fail:mercurial":
        # Send mercurial message to Lando
        logger.info(
            "Publishing code review hg failure.",
            revision=build.revision["id"],
            diff=build.diff_id,
        )
        try:
            lando_warnings.add_warning(
                LANDO_FAILURE_HG_MESSAGE, build.revision["id"], build.diff_id
            )
        except Exception as ex:
            logger.error(str(ex), exc_info=True)

    elif mode == "success":
        logger.info(
            "Begin publishing init warning message to lando.",
            revision=build.revision["id"],
            diff=build.diff_id,
        )
        try:
            lando_warnings.add_warning(
                LANDO_WARNING_MESSAGE, build.revision["id"], build.diff_id
            )
        except Exception as ex:
            logger.error(str(ex), exc_info=True)
    else:
        logger.info("Nothing to publish on Lando", mode=mode, build=build)
