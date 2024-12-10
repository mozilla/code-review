import asyncio
import os

import structlog
from libmozdata.lando import LandoWarnings
from libmozdata.phabricator import BuildState, UnitResult, UnitResultState
from libmozevent.bus import MessageBus
from libmozevent.mercurial import MercurialWorker, Repository
from libmozevent.monitoring import Monitoring
from libmozevent.phabricator import (
    PhabricatorActions,
    PhabricatorBuild,
    PhabricatorBuildState,
)
from libmozevent.pulse import PulseListener
from libmozevent.utils import run_tasks
from libmozevent.web import WebServer

from code_review_events import (
    MONITORING_PERIOD,
    QUEUE_BUGBUG,
    QUEUE_BUGBUG_TRY_PUSH,
    QUEUE_MERCURIAL,
    QUEUE_MERCURIAL_APPLIED,
    QUEUE_MONITORING,
    QUEUE_MONITORING_COMMUNITY,
    QUEUE_PHABRICATOR_RESULTS,
    QUEUE_PULSE_AUTOLAND,
    QUEUE_PULSE_BUGBUG_TEST_SELECT,
    QUEUE_PULSE_MOZILLA_CENTRAL,
    QUEUE_PULSE_TRY_TASK_END,
    QUEUE_WEB_BUILDS,
    community_taskcluster_config,
    taskcluster_config,
)
from code_review_events.bugbug_utils import BugbugUtils
from code_review_tools import heroku

logger = structlog.get_logger(__name__)

PULSE_TASK_GROUP_RESOLVED = "exchange/taskcluster-queue/v1/task-group-resolved"
PULSE_TASK_COMPLETED = "exchange/taskcluster-queue/v1/task-completed"
PULSE_TASK_FAILED = "exchange/taskcluster-queue/v1/task-failed"

LANDO_WARNING_MESSAGE = "Static analysis and linting are still in progress."
LANDO_FAILURE_MESSAGE = (
    "Static analysis and linting did not run due to a generic failure."
)
LANDO_FAILURE_HG_MESSAGE = (
    "Static analysis and linting did not run due to failure in applying the patch."
)
LANDO_FAILURE_EXPIRED = "Static analysis and linting did not run due to expired patch."

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_PATH = os.environ.get("VERSION_PATH", os.path.join(BASE_DIR, "version.json"))


class CodeReview(PhabricatorActions):
    """
    Code review workflow, receiving build notifications from HarborMaster
    and pushing on Try repositories
    """

    def __init__(
        self,
        lando_url,
        lando_publish_generic_failure,
        publish=False,
        user_blacklist=[],
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.publish = publish
        logger.info(
            "Phabricator publication is {}".format(
                self.publish and "enabled" or "disabled"
            )
        )

        self.publish_lando = True if lando_url is not None else False
        self.lando_publish_failure = lando_publish_generic_failure
        if self.publish_lando:
            logger.info("Publishing warnings to lando is enabled!")
            self.lando_warnings = LandoWarnings(
                api_url=lando_url,
                api_key=kwargs["api_key"],
            )
            if self.lando_publish_failure:
                logger.info("Publishing all failures to lando is enabled!")

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
        self.bus.add_queue(QUEUE_PHABRICATOR_RESULTS, redis=True)
        self.bus.add_queue(QUEUE_MERCURIAL_APPLIED, redis=True)

    def get_repositories(self, repositories, cache_root, default_ssh_key=None):
        """
        Configure repositories, and index them by phid
        """

        def _build_conf(config):
            # Use the default ssh key when specific repo key is not available
            if config.get("ssh_key") is None:
                config["ssh_key"] = default_ssh_key
            assert config["ssh_key"] is not None, "Missing ssh key"
            return config

        repository_mapping = {
            phab_repo["phid"]: Repository(_build_conf(conf), cache_root)
            for phab_repo in self.api.list_repositories()
            for conf in repositories
            if phab_repo["fields"]["name"] == conf["name"]
        }
        assert len(repository_mapping) > 0, "No repositories configured"

        assert len(repositories) == len(
            repository_mapping
        ), "Repositories {} couldn't be found on Phabricator".format(
            ", ".join(
                set(r["name"] for r in repositories)
                - set(r.name for r in repository_mapping.values())
            )
        )

        logger.info(
            "Configured repositories",
            names=[r.name for r in repository_mapping.values()],
        )
        return repository_mapping

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

            # Send Build in progress to Lando
            if self.publish_lando:
                logger.info(
                    "Begin publishing init warning message to lando.",
                    revision=build.revision["id"],
                    diff=build.diff_id,
                )
                try:
                    self.lando_warnings.add_warning(
                        LANDO_WARNING_MESSAGE, build.revision["id"], build.diff_id
                    )
                except Exception as ex:
                    logger.error(str(ex), exc_info=True)

        elif build.state == PhabricatorBuildState.Queued:
            # Requeue when nothing changed for now
            await self.bus.send(QUEUE_WEB_BUILDS, build)

        elif build.state == PhabricatorBuildState.Expired:
            # Report expired bug as not processed
            await self.bus.send(QUEUE_PHABRICATOR_RESULTS, ("fail:expired", build, {}))

    def is_blacklisted(self, revision: dict):
        """Check if the revision author is in blacklisted"""
        author = self.user_blacklist.get(revision["fields"]["authorPHID"])
        if author is None:
            return False

        logger.info(
            "Revision from a blacklisted user", revision=revision["id"], author=author
        )
        return True

    async def publish_results(self, payload):
        if not self.publish:
            logger.debug("Skipping Phabricator publication")
            return

        mode, build, extras = payload
        logger.debug("Publishing a Phabricator build update", mode=mode, build=build)

        def _send_failure(
            error_code, phabricator_state, phabricator_message, lando_message
        ):
            """Send error message on both phabricator & Lando"""
            failure = UnitResult(
                namespace="code-review",
                name=error_code,
                result=phabricator_state,
                details=phabricator_message,
                format="remarkup",
                duration=extras.get("duration", 0),
            )
            if self.lando_publish_failure:
                # Send general failure message to Lando
                if self.publish_lando:
                    logger.info(
                        "Publishing code review failure.",
                        code=error_code,
                        revision=build.revision["id"],
                        diff=build.diff_id,
                    )
                    try:
                        self.lando_warnings.add_warning(
                            lando_message, build.revision["id"], build.diff_id
                        )
                    except Exception as ex:
                        logger.error(str(ex), exc_info=True)

            self.api.update_build_target(
                build.target_phid, BuildState.Fail, unit=[failure]
            )

        if mode == "fail:general":
            _send_failure(
                error_code="general",
                phabricator_state=UnitResultState.Broken,
                phabricator_message="WARNING: An error occurred in the code review bot.\n\n```{}```".format(
                    extras["message"]
                ),
                lando_message=LANDO_FAILURE_MESSAGE,
            )

        elif mode == "fail:mercurial":
            extra_content = ""
            if build.missing_base_revision:
                extra_content = f" because the parent revision ({build.base_revision}) does not exist on mozilla-unified. If possible, you should publish that revision"

            _send_failure(
                error_code="mercurial",
                phabricator_state=UnitResultState.Fail,
                phabricator_message="WARNING: The code review bot failed to apply your patch{}.\n\n```{}```".format(
                    extra_content, extras["message"]
                ),
                lando_message=LANDO_FAILURE_HG_MESSAGE,
            )

        elif mode == "fail:expired":
            _send_failure(
                error_code="expired",
                phabricator_state=UnitResultState.Fail,
                phabricator_message="WARNING: The code review bot did not process your patch as it was published more than a day ago",
                lando_message=LANDO_FAILURE_EXPIRED,
            )

        elif mode == "test_result":
            result = UnitResult(
                namespace="code-review",
                name=extras["name"],
                result=extras["result"],
                details=extras["details"],
            )
            self.api.update_build_target(
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
                    details=f"WARNING: The base revision of your patch is not available in the current repository.\nYour patch has been rebased on central (revision {build.actual_base_revision}): issues may be positioned on the wrong lines.",
                )
                self.api.update_build_target(
                    build.target_phid, BuildState.Work, unit=[warning]
                )
                logger.debug(
                    "Missing base revision on PhabricatorBuild, adding a warning to Unit Tests section on Phabricator"
                )

            self.api.create_harbormaster_uri(
                build.target_phid,
                "treeherder",
                "CI (Treeherder) Jobs",
                extras["treeherder_url"],
            )

        elif mode == "work":
            self.api.update_build_target(build.target_phid, BuildState.Work)
            logger.info("Published public build as working", build=str(build))

        else:
            logger.warning("Unsupported publication", mode=mode, build=build)

    async def trigger_repository(self, payload: dict):
        """Trigger a code review from the ingestion task of a repository (all tasks are resolved)"""
        assert (
            payload["routing"]["exchange"] == PULSE_TASK_GROUP_RESOLVED
        ), "Message was not published to task-group-resolved"

        try:
            # Load first task in task group, check if it's on autoland or mozilla-central
            queue = taskcluster_config.get_service("queue")
            task_group_id = payload["body"]["taskGroupId"]
            logger.debug(
                "Checking repository for the task group", task_group_id=task_group_id
            )
            task = queue.task(task_group_id)
            repo_url = task["payload"]["env"].get("GECKO_HEAD_REPOSITORY")

            if repo_url == "https://hg.mozilla.org/integration/autoland":
                group_key = "AUTOLAND_TASK_GROUP_ID"
            elif repo_url == "https://hg.mozilla.org/mozilla-central":
                group_key = "MOZILLA_CENTRAL_TASK_GROUP_ID"
            else:
                logger.debug(
                    f"Repository {repo_url} is not supported", task=task_group_id
                )
                return

            # Trigger the autoland ingestion task
            env = taskcluster_config.secrets["APP_CHANNEL"]
            hooks = taskcluster_config.get_service("hooks")
            task = hooks.triggerHook(
                "project-relman",
                f"code-review-{env}",
                {group_key: task_group_id},
            )
            task_id = task["status"]["taskId"]
            logger.info(f"Triggered a new ingestion task from {repo_url}", id=task_id)
        except Exception as e:
            logger.warn(
                "Repository trigger failure",
                key=payload["routing"]["key"],
                error=str(e),
            )


class Events:
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

        community_config = taskcluster_config.secrets.get("taskcluster_community")
        test_selection_enabled = taskcluster_config.secrets.get(
            "test_selection_enabled", False
        )

        # Run webserver & pulse on web dyno or single instance
        if not heroku.in_dyno() or heroku.in_web_dyno():
            # Create web server
            self.webserver = WebServer(QUEUE_WEB_BUILDS, version_path=VERSION_PATH)
            self.webserver.register(self.bus)

            # Create pulse listeners
            exchanges = {}
            if taskcluster_config.secrets["autoland_enabled"]:
                logger.info("Autoland ingestion is enabled")
                # autoland ingestion
                exchanges[QUEUE_PULSE_AUTOLAND] = [
                    (PULSE_TASK_GROUP_RESOLVED, ["#.gecko-level-3.#"])
                ]
            if taskcluster_config.secrets["mozilla_central_enabled"]:
                logger.info("Mozilla-central ingestion is enabled")
                # autoland ingestion
                exchanges[QUEUE_PULSE_MOZILLA_CENTRAL] = [
                    (PULSE_TASK_GROUP_RESOLVED, ["#.gecko-level-3.#"])
                ]

            # Create pulse listeners for bugbug test selection task and unit test failures.
            if community_config is not None and test_selection_enabled:
                exchanges[QUEUE_PULSE_TRY_TASK_END] = [
                    (PULSE_TASK_COMPLETED, ["#.gecko-level-1.#"]),
                    (PULSE_TASK_FAILED, ["#.gecko-level-1.#"]),
                    # https://bugzilla.mozilla.org/show_bug.cgi?id=1599863
                    # (
                    #    "exchange/taskcluster-queue/v1/task-exception",
                    #    ["#.gecko-level-1.#"],
                    # ),
                ]

                self.community_pulse = PulseListener(
                    {
                        QUEUE_PULSE_BUGBUG_TEST_SELECT: [
                            (
                                "exchange/taskcluster-queue/v1/task-completed",
                                ["route.project.bugbug.test_select"],
                            )
                        ]
                    },
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
                    exchanges,
                    taskcluster_config.secrets["pulse_user"],
                    taskcluster_config.secrets["pulse_password"],
                )
                # Manually register to set queue as redis
                self.pulse.bus = self.bus
                if taskcluster_config.secrets["autoland_enabled"]:
                    self.bus.add_queue(QUEUE_PULSE_AUTOLAND, redis=True)
                if taskcluster_config.secrets["mozilla_central_enabled"]:
                    self.bus.add_queue(QUEUE_PULSE_MOZILLA_CENTRAL, redis=True)
            else:
                self.pulse = None

        else:
            self.bugbug_utils = None
            self.webserver = None
            self.pulse = None
            self.community_pulse = None
            logger.info("Skipping webserver, bugbug and pulse consumers")

            # Register queues for workers
            self.bus.add_queue(QUEUE_PULSE_AUTOLAND, redis=True)
            self.bus.add_queue(QUEUE_PULSE_MOZILLA_CENTRAL, redis=True)
            self.bus.add_queue(QUEUE_PULSE_BUGBUG_TEST_SELECT, redis=True)
            self.bus.add_queue(QUEUE_PULSE_TRY_TASK_END, redis=True)
            self.bus.add_queue(QUEUE_WEB_BUILDS, redis=True)

        # Lando publishing warnings
        lando_url = None
        lando_publish_generic_failure = False
        if taskcluster_config.secrets["LANDO"].get("publish", False):
            lando_url = taskcluster_config.secrets["LANDO"]["url"]
            lando_publish_generic_failure = taskcluster_config.secrets["LANDO"][
                "publish_failure"
            ]

        # Run work processes on worker dyno or single instance
        if not heroku.in_dyno() or heroku.in_worker_dyno():
            self.workflow = CodeReview(
                lando_url=lando_url,
                lando_publish_generic_failure=lando_publish_generic_failure,
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
                    taskcluster_config.secrets["repositories"],
                    cache_root,
                    default_ssh_key=taskcluster_config.secrets["ssh_key"],
                ),
                skippable_files=taskcluster_config.secrets["skippable_files"],
            )
            self.mercurial.register(self.bus)

            # Setup monitoring for newly created tasks
            self.monitoring = Monitoring(
                taskcluster_config,
                QUEUE_MONITORING,
                taskcluster_config.secrets["admins"],
                MONITORING_PERIOD,
            )
            self.monitoring.register(self.bus)

            # Setup monitoring for newly created community tasks
            if community_config is not None:
                self.community_monitoring = Monitoring(
                    community_taskcluster_config,
                    QUEUE_MONITORING_COMMUNITY,
                    taskcluster_config.secrets["admins"],
                    MONITORING_PERIOD,
                )
                self.community_monitoring.register(self.bus)
            else:
                self.community_monitoring = None

            self.bugbug_utils = BugbugUtils(self.workflow.api)
            self.bugbug_utils.register(self.bus)
        else:
            self.workflow = None
            self.mercurial = None
            self.monitoring = None
            self.community_monitoring = None
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
                # Send to phabricator results publication for normal processing and to bugbug for further analysis
                self.bus.dispatch(
                    QUEUE_MERCURIAL_APPLIED,
                    [QUEUE_PHABRICATOR_RESULTS, QUEUE_BUGBUG_TRY_PUSH],
                ),
            ]
            if taskcluster_config.secrets["autoland_enabled"]:
                # Trigger autoland tasks
                consumers.append(
                    self.bus.run(self.workflow.trigger_repository, QUEUE_PULSE_AUTOLAND)
                )
            if taskcluster_config.secrets["mozilla_central_enabled"]:
                # Trigger mozilla-central tasks
                consumers.append(
                    self.bus.run(
                        self.workflow.trigger_repository, QUEUE_PULSE_MOZILLA_CENTRAL
                    )
                )

        if self.bugbug_utils:
            consumers += [
                self.bus.run(self.bugbug_utils.process_build, QUEUE_BUGBUG),
                self.bus.run(self.bugbug_utils.process_push, QUEUE_BUGBUG_TRY_PUSH),
                self.bus.run(
                    self.bugbug_utils.got_try_task_end, QUEUE_PULSE_TRY_TASK_END
                ),
                self.bus.run(
                    self.bugbug_utils.got_bugbug_test_select_end,
                    QUEUE_PULSE_BUGBUG_TEST_SELECT,
                ),
            ]

        # Add mercurial task
        if self.mercurial:
            consumers.append(self.mercurial.run())

        # Add monitoring task
        if self.monitoring:
            consumers.append(self.monitoring.run())

        # Add community monitoring task
        if self.community_monitoring:
            consumers.append(self.community_monitoring.run())

        # Add pulse listener for task results.
        if self.pulse:
            consumers.append(self.pulse.run())

        # Add communitytc pulse listener for test selection results.
        if self.community_pulse:
            consumers.append(self.community_pulse.run())

        # Start the web server in its own process
        if self.webserver:
            self.webserver.start()

        loop = asyncio.get_event_loop()

        if consumers:
            # Run all tasks concurrently
            try:
                logger.info(f"Running {len(consumers)} message consumers")
                run_tasks(consumers, bus_to_restore=self.bus)
            except asyncio.CancelledError:
                logger.warning(
                    "Consumers have been stopped. Shutting down code review events…"
                )
        else:
            # Keep the web server process running
            asyncio.get_event_loop().run_forever()

        # Make sure any pending task is run.
        run_tasks([task for task in asyncio.all_tasks(loop) if not task.cancelled])

        # Stop the webserver when other async processes are stopped
        if self.webserver:
            self.webserver.stop()
