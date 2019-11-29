# -*- coding: utf-8 -*-
import asyncio

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

from code_review_events import MONITORING_PERIOD
from code_review_events import QUEUE_BUGBUG
from code_review_events import QUEUE_BUGBUG_TRY_PUSH
from code_review_events import QUEUE_MERCURIAL
from code_review_events import QUEUE_MERCURIAL_APPLIED
from code_review_events import QUEUE_MONITORING
from code_review_events import QUEUE_PHABRICATOR_RESULTS
from code_review_events import QUEUE_PULSE
from code_review_events import QUEUE_PULSE_BUGBUG_TEST_SELECT
from code_review_events import QUEUE_PULSE_TRY_TASK_END
from code_review_events import QUEUE_WEB_BUILDS
from code_review_events.bugbug_utils import BugbugUtils
from code_review_tools import heroku

logger = structlog.get_logger(__name__)

PULSE_TASK_GROUP_RESOLVED = "exchange/taskcluster-queue/v1/task-group-resolved"
PULSE_TASK_COMPLETED = "exchange/taskcluster-queue/v1/task-completed"
PULSE_TASK_FAILED = "exchange/taskcluster-queue/v1/task-failed"


class CodeReview(PhabricatorActions):
    """
    Code review workflow, receiving build notifications from HarborMaster
    and pushing on Try repositories
    """

    def __init__(self, publish=False, user_blacklist=[], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.publish = publish
        logger.info(
            "Phabricator publication is {}".format(
                self.publish and "enabled" or "disabled"
            )
        )

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
        self.bus.add_queue(QUEUE_MERCURIAL_APPLIED)

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

    async def process_build(self, build):
        """
        Code review workflow to load all necessary information from Phabricator builds
        received from the webserver
        """
        assert build is not None, "Invalid payload"
        assert isinstance(build, PhabricatorBuild)

        # Update its state
        self.update_state(build)

        if build.state == PhabricatorBuildState.Public:

            # Check if the author is not blacklisted
            if self.is_blacklisted(build.revision):
                return

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
                return

            # Then send the build toward next stage
            logger.info("Send build to Mercurial", build=str(build))
            await self.bus.send(QUEUE_MERCURIAL, build)

            # Report public bug as 'working' (in progress)
            await self.bus.send(QUEUE_PHABRICATOR_RESULTS, ("work", build, {}))

            # Send to bugbug workflow
            await self.bus.send(QUEUE_BUGBUG, build)

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

    async def dispatch_mercurial_applied(self, payload):
        # Send to phabricator results publication for normal processing
        await self.bus.send(QUEUE_PHABRICATOR_RESULTS, payload)

        # Send to bugbug for further analysis
        await self.bus.send(QUEUE_BUGBUG_TRY_PUSH, payload)

    def publish_results(self, payload):
        if not self.publish:
            logger.debug("Skipping Phabricator publication")
            return

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

        elif mode == "test_result":
            result = UnitResult(
                namespace="code-review", name=extras["name"], result=extras["result"]
            )
            self.api.update_build_target(
                build.target_phid, BuildState.Work, unit=[result]
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

    async def parse_pulse(self, payload):
        routing = payload["routing"]

        # Process autoland payloads
        if routing["exchange"] == PULSE_TASK_GROUP_RESOLVED:
            try:
                self.trigger_autoland(payload["body"])
            except Exception as e:
                logger.warn(
                    "Autoland trigger failure", key=routing["key"], error=str(e)
                )
        else:
            # Send to bugbug
            await self.bus.send(QUEUE_PULSE_TRY_TASK_END, payload)

    def trigger_autoland(self, body: dict):
        """
        Trigger a code review autoland ingestion task
        If the task is an autoland decision task
        """
        # Load first task in task group, check if it's an autoland
        queue = taskcluster_config.get_service("queue")
        task_group_id = body["taskGroupId"]
        logger.info("Checking autoland task", task_group_id=task_group_id)
        task = queue.task(task_group_id)
        repo = task["payload"]["env"].get("GECKO_HEAD_REPOSITORY")
        if repo != "https://hg.mozilla.org/integration/autoland":
            logger.info("Not an autoland task", task=task_group_id)
            return

        # Trigger the autoland ingestion task
        env = taskcluster_config.secrets["APP_CHANNEL"]
        hooks = taskcluster_config.get_service("hooks")
        task = hooks.triggerHook(
            "project-relman",
            f"code-review-{env}",
            {"AUTOLAND_TASK_GROUP_ID": task_group_id},
        )
        task_id = task["status"]["taskId"]
        logger.info("Triggered a new autoland ingestion task", id=task_id)


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

            # Create pulse listener
            exchanges = []
            if taskcluster_config.secrets["autoland_enabled"]:
                logger.info("Autoland ingestion is enabled")
                exchanges += [
                    # autoland ingestion
                    (PULSE_TASK_GROUP_RESOLVED, ["#.gecko-level-3.#"])
                ]
            if publish:
                # unit test failures
                exchanges += [(PULSE_TASK_COMPLETED, ["*.*.gecko-level-3._"])]

            # Create pulse listeners for bugbug test selection task and unit test failures.
            community_config = taskcluster_config.secrets.get("taskcluster_community")
            test_selection_enabled = taskcluster_config.secrets.get(
                "test_selection_enabled", False
            )
            if community_config is not None and test_selection_enabled:
                exchanges += [
                    (PULSE_TASK_COMPLETED, ["#.gecko-level-1.#"]),
                    (PULSE_TASK_FAILED, ["#.gecko-level-1.#"]),
                    # https://bugzilla.mozilla.org/show_bug.cgi?id=1599863
                    # (
                    #    "exchange/taskcluster-queue/v1/task-exception",
                    #    ["#.gecko-level-1.#"],
                    # ),
                ]

                self.community_pulse = PulseListener(
                    QUEUE_PULSE_BUGBUG_TEST_SELECT,
                    [
                        (
                            "exchange/taskcluster-queue/v1/task-completed",
                            ["route.project.relman.bugbug.test_select"],
                        )
                    ],
                    taskcluster_config.secrets["communitytc_pulse_user"],
                    taskcluster_config.secrets["communitytc_pulse_password"],
                    "communitytc",
                )
                # Manually register to set queue as redis
                self.community_pulse.bus = self.bus
                self.bus.add_queue(QUEUE_PULSE_BUGBUG_TEST_SELECT, redis=True)
                self.bus.add_queue(QUEUE_PULSE_TRY_TASK_END, redis=True)
            else:
                self.community_pulse = None

            if exchanges:
                self.pulse = PulseListener(
                    QUEUE_PULSE,
                    exchanges,
                    taskcluster_config.secrets["pulse_user"],
                    taskcluster_config.secrets["pulse_password"],
                )
                # Manually register to set queue as redis
                self.pulse.bus = self.bus
                self.bus.add_queue(QUEUE_PULSE, redis=True)
            else:
                self.pulse = None

        else:
            self.bugbug_utils = None
            self.webserver = None
            self.pulse = None
            self.community_pulse = None
            logger.info("Skipping webserver, bugbug and pulse consumers")

            # Register queues for workers
            self.bus.add_queue(QUEUE_PULSE, redis=True)
            self.bus.add_queue(QUEUE_PULSE_BUGBUG_TEST_SELECT, redis=True)
            self.bus.add_queue(QUEUE_PULSE_TRY_TASK_END, redis=True)
            self.bus.add_queue(QUEUE_WEB_BUILDS, redis=True)

        # Run work processes on worker dyno or single instance
        if not heroku.in_dyno() or heroku.in_worker_dyno():
            self.workflow = CodeReview(
                api_key=taskcluster_config.secrets["PHABRICATOR"]["api_key"],
                url=taskcluster_config.secrets["PHABRICATOR"]["url"],
                publish=publish,
                user_blacklist=taskcluster_config.secrets["user_blacklist"],
            )
            self.workflow.register(self.bus)

            # Build mercurial worker and queue
            self.mercurial = MercurialWorker(
                QUEUE_MERCURIAL,
                QUEUE_MERCURIAL_APPLIED,
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

            self.bugbug_utils = BugbugUtils()
            self.bugbug_utils.register(self.bus)
        else:
            self.workflow = None
            self.mercurial = None
            self.monitoring = None
            self.bugbug_utils = None
            logger.info("Skipping workers consumers")

    def run(self):
        consumers = []

        # Code review main workflow
        if self.workflow:
            consumers += [
                # Process Phabricator build received from webserver
                self.bus.run(self.workflow.process_build, QUEUE_WEB_BUILDS),
                # Publish results on Phabricator
                self.bus.run(self.workflow.publish_results, QUEUE_PHABRICATOR_RESULTS),
                # Parse and redirect pulse messages
                self.bus.run(self.workflow.parse_pulse, QUEUE_PULSE),
                self.bus.run(
                    self.workflow.dispatch_mercurial_applied, QUEUE_MERCURIAL_APPLIED
                ),
            ]

        if self.bugbug_utils:
            consumers += [
                self.bugbug_utils.run(),
                self.bus.run(self.bugbug_utils.process_push, QUEUE_BUGBUG_TRY_PUSH),
                self.bus.run(
                    self.bugbug_utils.got_try_task_end,
                    QUEUE_PULSE_TRY_TASK_END,
                    sequential=False,
                ),
                self.bus.run(
                    self.bugbug_utils.got_bugbug_test_select_end,
                    QUEUE_PULSE_BUGBUG_TEST_SELECT,
                    sequential=False,
                ),
            ]

        # Add mercurial task
        if self.mercurial:
            consumers.append(self.mercurial.run())

        # Add monitoring task
        if self.monitoring:
            consumers.append(self.monitoring.run())

        # Add pulse listener for task results.
        if self.pulse:
            consumers.append(self.pulse.run())

        # Add communitytc pulse listener for test selection results.
        if self.community_pulse:
            consumers.append(self.community_pulse.run())

        # Start the web server in its own process
        if self.webserver:
            self.webserver.start()

        if consumers:
            # Run all tasks concurrently
            run_tasks(consumers)
        else:
            # Keep the web server process running
            asyncio.get_event_loop().run_forever()

        # Stop the webserver when other async processes are stopped
        if self.webserver:
            self.webserver.stop()
