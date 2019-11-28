# -*- coding: utf-8 -*-
import random

import structlog
from libmozdata.phabricator import BuildState
from libmozdata.phabricator import UnitResult
from libmozdata.phabricator import UnitResultState
from libmozevent import taskcluster_config
from libmozevent.bus import MessageBus
from libmozevent.mercurial import MercurialWorker
from libmozevent.mercurial import Repository
from libmozevent.monitoring import Monitoring
from libmozevent.phabricator import PhabricatorActions
from libmozevent.phabricator import PhabricatorBuild
from libmozevent.phabricator import PhabricatorBuildState
from libmozevent.pulse import PulseListener
from libmozevent.utils import run_tasks
from libmozevent.web import WebServer
from taskcluster import Hooks

from code_review_events import MONITORING_PERIOD
from code_review_events import QUEUE_MERCURIAL
from code_review_events import QUEUE_MONITORING
from code_review_events import QUEUE_PHABRICATOR_RESULTS
from code_review_events import QUEUE_PULSE
from code_review_events import QUEUE_WEB_BUILDS
from code_review_tools import heroku

logger = structlog.get_logger(__name__)


class CodeReview(PhabricatorActions):
    """
    Code review workflow, receiving build notifications from HarborMaster
    and pushing on Try repositories
    """

    def __init__(
        self,
        publish=False,
        risk_analysis_reviewers=[],
        community_config=None,
        user_blacklist=[],
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.publish = publish
        logger.info(
            "Phabricator publication is {}".format(
                self.publish and "enabled" or "disabled"
            )
        )

        # Setup Taskcluster community hooks for risk analysis
        if community_config is not None:
            self.community_hooks = Hooks(
                {
                    "rootUrl": "https://community-tc.services.mozilla.com",
                    "credentials": {
                        "clientId": community_config["client_id"],
                        "accessToken": community_config["access_token"],
                    },
                }
            )
            logger.info("Risk analysis trigger is enabled")
        else:
            self.community_hooks = None
            logger.info("No taskcluster_community in secret, risk analysis is disabled")

        self.risk_analysis_reviewers = risk_analysis_reviewers

        # Load the blacklisted users
        if user_blacklist:
            self.user_blacklist = {
                user["phid"]: user["fields"]["username"]
                for user in self.api.search_users(
                    constraints={"usernames": user_blacklist}
                )
            }
            logger.info("Blacklisted users", names=self.user_blacklist.values())
        else:
            self.user_blacklist = {}
            logger.info("No blacklisted user")

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
            assert build is not None, "Invalid payload"
            assert isinstance(build, PhabricatorBuild)

            # Update its state
            self.update_state(build)

            if build.state == PhabricatorBuildState.Public:

                # Check if the author is not blacklisted
                if self.is_blacklisted(build.revision):
                    continue

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

                # Report public bug as 'working' (in progress)
                await self.bus.send(QUEUE_PHABRICATOR_RESULTS, ("work", build, {}))

                # Start risk analysis
                await self.start_risk_analysis(build)

                # Start test selection
                await self.start_test_selection(build)

            elif build.state == PhabricatorBuildState.Queued:
                # Requeue when nothing changed for now
                await self.bus.send(QUEUE_WEB_BUILDS, build)

    def is_blacklisted(self, revision: dict):
        """Check if the revision author is in blacklisted"""
        author = self.user_blacklist.get(revision["fields"]["authorPHID"])
        if author is None:
            return False

        logger.info(
            "Revision from a blacklisted user", revision=revision["id"], author=author
        )
        return True

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

    def parse_pulse(self, payload):
        assert self.publish is True, "Publication disabled"

    async def start_risk_analysis(self, build):
        """
        Run risk analysis by triggering a Taskcluster hook
        """
        assert isinstance(build, PhabricatorBuild)
        assert build.state == PhabricatorBuildState.Public
        try:
            if self.should_run_risk_analysis(build):
                task = self.community_hooks.triggerHook(
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
        if self.community_hooks is None:
            return False

        usernames = set(
            [reviewer["fields"]["username"] for reviewer in build.reviewers]
        )
        return len(usernames.intersection(self.risk_analysis_reviewers)) > 0

    def should_run_test_selection(self, build):
        """
        Check if we should trigger a test selection for this revision:
        * randomly for a subset of revisions
        """
        if self.community_hooks is None:
            return False

        return random.random() < taskcluster_config.secrets.get(
            "test_selection_share", 0.0
        )

    async def start_test_selection(self, build):
        """
        Run test selection by triggering a Taskcluster hook
        """
        assert isinstance(build, PhabricatorBuild)
        assert build.state == PhabricatorBuildState.Public
        try:
            if self.should_run_test_selection(build):
                task = self.community_hooks.triggerHook(
                    "project-relman", "bugbug-test-select", {"DIFF_ID": build.diff_id}
                )
                task_id = task["status"]["taskId"]
                logger.info("Triggered a new test selection task", id=task_id)

                # Send task to monitoring
                await self.bus.send(
                    QUEUE_MONITORING, ("project-relman", "bugbug-test-select", task_id)
                )
        except Exception as e:
            logger.error("Failed to trigger test selection task", error=str(e))


class Events(object):
    """
    Listen to HTTP notifications from phabricator and trigger new try jobs
    """

    def __init__(self, cache_root):
        # Create message bus shared amongst processes
        self.bus = MessageBus()

        publish = taskcluster_config.secrets["PHABRICATOR"].get("publish", False)

        # Check the redis support is enabled on Heroku
        if heroku.in_dyno():
            assert self.bus.redis_enabled is True, "Need Redis on Heroku"

        # Run webserver & pulse on web dyno or single instance
        if not heroku.in_dyno() or heroku.in_web_dyno():

            # Create web server
            self.webserver = WebServer(QUEUE_WEB_BUILDS)
            self.webserver.register(self.bus)

            # Create pulse listener for unit test failures
            self.pulse = PulseListener(
                QUEUE_PULSE,
                "exchange/taskcluster-queue/v1/task-completed",
                "*.*.gecko-level-3._",
                taskcluster_config.secrets["pulse_user"],
                taskcluster_config.secrets["pulse_password"],
            )

            # Manually register to set queue as redis
            self.pulse.bus = self.bus
            self.bus.add_queue(QUEUE_PULSE, redis=True)
        else:
            self.webserver = None
            self.pulse = None
            logger.info("Skipping webserver & pulse consumers")

            # Register queues for workers
            self.bus.add_queue(QUEUE_PULSE, redis=True)
            self.bus.add_queue(QUEUE_WEB_BUILDS, redis=True)

        # Run work processes on worker dyno or single instance
        if not heroku.in_dyno() or heroku.in_worker_dyno():
            self.workflow = CodeReview(
                api_key=taskcluster_config.secrets["PHABRICATOR"]["api_key"],
                url=taskcluster_config.secrets["PHABRICATOR"]["url"],
                publish=publish,
                risk_analysis_reviewers=taskcluster_config.secrets.get(
                    "risk_analysis_reviewers", []
                ),
                community_config=taskcluster_config.secrets.get(
                    "taskcluster_community"
                ),
                user_blacklist=taskcluster_config.secrets["user_blacklist"],
            )
            self.workflow.register(self.bus)

            # Build mercurial worker and queue
            self.mercurial = MercurialWorker(
                QUEUE_MERCURIAL,
                QUEUE_PHABRICATOR_RESULTS,
                repositories=self.workflow.get_repositories(
                    taskcluster_config.secrets["repositories"], cache_root
                ),
            )
            self.mercurial.register(self.bus)

            # Setup monitoring for newly created tasks
            self.monitoring = Monitoring(
                QUEUE_MONITORING,
                taskcluster_config.secrets["admins"],
                MONITORING_PERIOD,
            )
            self.monitoring.register(self.bus)
        else:
            self.workflow = None
            self.mercurial = None
            self.monitoring = None
            logger.info("Skipping workers consumers")

    def run(self):
        consumers = []

        # Code review main workflow
        if self.workflow:
            consumers.append(self.workflow.run())

            # Publish results on Phabricator
            if self.workflow.publish:
                consumers += [
                    self.bus.run(
                        self.workflow.publish_results, QUEUE_PHABRICATOR_RESULTS
                    ),
                    self.bus.run(self.workflow.parse_pulse, QUEUE_PULSE),
                ]

        # Add mercurial task
        if self.mercurial:
            consumers.append(self.mercurial.run())

        # Add monitoring task
        if self.monitoring:
            consumers.append(self.monitoring.run())

        # Add pulse listener
        if self.pulse:
            consumers.append(self.pulse.run())

        # Start the web server in its own process
        if self.webserver:
            self.webserver.start()

        # Run all tasks concurrently
        run_tasks(consumers)

        # Stop the webserver when other async processes are stopped
        if self.webserver:
            self.webserver.stop()
