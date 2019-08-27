# -*- coding: utf-8 -*-
import structlog
from libmozdata.phabricator import BuildState
from libmozdata.phabricator import UnitResult
from libmozdata.phabricator import UnitResultState
from libmozevent import taskcluster_config
from libmozevent.mercurial import Repository
from libmozevent.phabricator import PhabricatorActions
from libmozevent.phabricator import PhabricatorBuild
from libmozevent.phabricator import PhabricatorBuildState

from code_review_events import QUEUE_MERCURIAL
from code_review_events import QUEUE_MONITORING
from code_review_events import QUEUE_PHABRICATOR_RESULTS
from code_review_events import QUEUE_WEB_BUILDS

logger = structlog.get_logger(__name__)


class CodeReview(PhabricatorActions):
    """
    Code review workflow, receiving build notifications from HarborMaster
    and pushing on Try repositories
    """

    def __init__(self, publish=False, risk_analysis_reviewers=[], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.publish = publish
        logger.info(
            "Phabricator publication is {}".format(
                self.publish and "enabled" or "disabled"
            )
        )

        self.hooks = taskcluster_config.get_service("hooks")
        self.risk_analysis_reviewers = risk_analysis_reviewers

    def register(self, bus):
        self.bus = bus
        self.bus.add_queue(QUEUE_PHABRICATOR_RESULTS)

    def get_repositories(self, repositories, cache_root):
        """
        Configure repositories, and index them by phid
        """
        repositories = {
            phab_repo["phid"]: Repository(conf, cache_root)
            for phab_repo in self.api.list_repositories()
            for conf in repositories
            if phab_repo["fields"]["name"] == conf["name"]
        }
        assert len(repositories) > 0, "No repositories configured"
        logger.info(
            "Configured repositories", names=[r.name for r in repositories.values()]
        )
        return repositories

    async def run(self):
        """
        Code review workflow to load all necessary information from Phabricator builds
        received from the webserver
        """
        while True:

            # Receive build from webserver
            build = await self.bus.receive(QUEUE_WEB_BUILDS)
            assert isinstance(build, PhabricatorBuild)

            # Update its state
            self.update_state(build)

            if build.state == PhabricatorBuildState.Public:
                # When the build is public, load needed details
                try:
                    self.load_patches_stack(build)
                    logger.info("Loaded stack of patches", build=str(build))

                    self.load_reviewers(build)
                    logger.info("Loaded reviewers", build=str(build))
                except Exception as e:
                    logger.warning(
                        "Failed to load build details", build=str(build), error=str(e)
                    )
                    continue

                # Then send the build toward next stage
                logger.info("Send build to Mercurial", build=str(build))
                await self.bus.send(QUEUE_MERCURIAL, build)

                # Report public bug as working
                await self.bus.send(QUEUE_PHABRICATOR_RESULTS, ("work", build, {}))

                # Start risk analysis
                await self.start_risk_analysis(build)

            elif build.state == PhabricatorBuildState.Queued:
                # Requeue when nothing changed for now
                await self.bus.send(QUEUE_WEB_BUILDS, build)

    def publish_results(self, payload):
        assert self.publish is True, "Publication disabled"
        mode, build, extras = payload
        logger.debug("Publishing a Phabricator build update", mode=mode, build=build)

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
            self.api.update_build_target(
                build.target_phid, BuildState.Fail, unit=[failure]
            )

        elif mode == "fail:mercurial":
            failure = UnitResult(
                namespace="code-review",
                name="mercurial",
                result=UnitResultState.Fail,
                details="WARNING: The code review bot failed to apply your patch.\n\n```{}```".format(
                    extras["message"]
                ),
                format="remarkup",
                duration=extras.get("duration", 0),
            )
            self.api.update_build_target(
                build.target_phid, BuildState.Fail, unit=[failure]
            )

        elif mode == "success":
            self.api.create_harbormaster_uri(
                build.target_phid,
                "treeherder",
                "Treeherder Jobs",
                extras["treeherder_url"],
            )

        elif mode == "work":
            self.api.update_build_target(build.target_phid, BuildState.Work)
            logger.info("Published public build as working", build=str(build))

        else:
            logger.warning("Unsupported publication", mode=mode, build=build)

        return True

    async def start_risk_analysis(self, build):
        """
        Run risk analysis by triggering a Taskcluster hook
        """
        assert isinstance(build, PhabricatorBuild)
        assert build.state == PhabricatorBuildState.Public
        try:
            if self.should_run_risk_analysis(build):
                task = self.hooks.triggerHook(
                    "project-relman",
                    "bugbug-classify-patch",
                    {"DIFF_ID": build.diff_id},
                )
                task_id = task["status"]["taskId"]
                logger.info("Triggered a new risk analysis task", id=task_id)

                # Send task to monitoring
                await self.bus.send(
                    QUEUE_MONITORING,
                    ("project-relman", "bugbug-classify-patch", task_id),
                )
        except Exception as e:
            logger.error("Failed to trigger risk analysis task", error=str(e))

    def should_run_risk_analysis(self, build):
        """
        Check if we should trigger a risk analysis for this revision:
        * when the revision is being reviewed by one of some specific reviewers
        """
        usernames = set(
            [reviewer["fields"]["username"] for reviewer in build.reviewers]
        )
        return len(usernames.intersection(self.risk_analysis_reviewers)) > 0
