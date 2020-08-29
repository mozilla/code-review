# -*- coding: utf-8 -*-
import asyncio
import random

import jsone
import jsonschema
import structlog
from libmozdata.phabricator import UnitResultState
from libmozevent.phabricator import PhabricatorBuild
from libmozevent.phabricator import PhabricatorBuildState
from libmozevent.storage import EphemeralStorage

from code_review_events import QUEUE_BUGBUG
from code_review_events import QUEUE_BUGBUG_TRY_PUSH
from code_review_events import QUEUE_MONITORING_COMMUNITY
from code_review_events import QUEUE_PHABRICATOR_RESULTS
from code_review_events import community_taskcluster_config
from code_review_events import taskcluster_config
from code_review_tools.treeherder import get_job_url

logger = structlog.get_logger(__name__)


# If we triggered an analysis or tests more than 7 hours ago, we can forget about them.
EPHEMERAL_STORAGE_EXPIRATION = 25200


class BugbugUtils:
    def __init__(self, phabricator_api):
        self.phabricator_deployment = taskcluster_config.secrets.get(
            "bugbug_phabricator_deployment", "prod"
        )
        assert self.phabricator_deployment in (
            "prod",
            "dev",
        ), f"{self.phabricator_deployment} should be either 'prod' or 'dev'"

        self.test_selection_enabled = taskcluster_config.secrets.get(
            "test_selection_enabled", False
        )
        self.test_selection_share = taskcluster_config.secrets.get(
            "test_selection_share", 0.0
        )
        self.test_selection_notify_addresses = taskcluster_config.secrets.get(
            "test_selection_notify_addresses", []
        )

        risk_analysis_users = taskcluster_config.secrets.get("risk_analysis_users", [])

        if len(risk_analysis_users) > 0:
            self.risk_analysis_users = {
                user["phid"]: user["fields"]["username"]
                for user in phabricator_api.search_users(
                    constraints={"usernames": risk_analysis_users}
                )
            }
        else:
            self.risk_analysis_users = {}

        # A map from try push task group to its linked Phabricator build.
        self.task_group_to_push = EphemeralStorage(
            "bugbug:task_group_to_push", EPHEMERAL_STORAGE_EXPIRATION
        )
        # A map from build phid to try revision.
        self.diff_to_push = EphemeralStorage(
            "bugbug:diff_to_push", EPHEMERAL_STORAGE_EXPIRATION
        )

        # Setup Taskcluster community hooks for risk analysis
        community_config = taskcluster_config.secrets.get("taskcluster_community")
        if community_config is not None:
            self.community_tc = {
                "hooks": community_taskcluster_config.get_service("hooks"),
                "queue": community_taskcluster_config.get_service("queue"),
            }

            if self.test_selection_enabled:
                logger.info("Risk analysis and test selection triggers are enabled")
            else:
                logger.info(
                    "Risk analysis trigger is enabled, test selection trigger is disabled"
                )
        else:
            self.community_tc = None
            logger.info(
                "No taskcluster_community in secret, risk analysis and test selection triggers are disabled"
            )

        self.notify_service = taskcluster_config.get_service("notify", use_async=True)
        self.index_service = taskcluster_config.get_service("index")
        self.hooks_service = taskcluster_config.get_service("hooks")
        self.queue_service = taskcluster_config.get_service("queue")

    def register(self, bus):
        self.bus = bus
        self.bus.add_queue(QUEUE_BUGBUG)
        self.bus.add_queue(QUEUE_BUGBUG_TRY_PUSH)

    async def process_push(self, payload):
        mode, build, extras = payload
        if mode != "success":
            return

        # Store the push revision and build, so we can use it after bugbug
        # selects tests to add.
        logger.info(
            "Diff added to the list of diffs we pushed to try", diff_id=build.diff_id
        )
        await self.diff_to_push.set(
            str(build.diff_id),
            {
                "revision": extras["revision"],
                "treeherder_url": extras["treeherder_url"],
                "build": build,
            },
        )

        # Start test selection
        await self.start_test_selection(build, extras["revision"])

    async def process_build(self, build):
        assert build is not None, "Invalid payload"
        assert isinstance(build, PhabricatorBuild)

        # Start risk analysis
        await self.start_risk_analysis(build)

    def should_run_risk_analysis(self, build):
        """
        Check if we should trigger a risk analysis for this revision:
        * when the reviewers or the author of the revision are in a list of specific users
        """
        if self.community_tc is None:
            return False

        userPHIDs = [
            reviewer["reviewerPHID"]
            for reviewer in build.revision["attachments"]["reviewers"]["reviewers"]
        ]

        userPHIDs.append(build.revision["fields"]["authorPHID"])

        return any(userPHID in self.risk_analysis_users for userPHID in userPHIDs)

    async def start_risk_analysis(self, build: PhabricatorBuild):
        """
        Run risk analysis by triggering a Taskcluster hook
        """
        assert build.state == PhabricatorBuildState.Public
        try:
            if not self.should_run_risk_analysis(build):
                return

            task = self.community_tc["hooks"].triggerHook(
                "project-bugbug",
                "bugbug-classify-patch",
                {
                    "PHABRICATOR_DEPLOYMENT": self.phabricator_deployment,
                    "DIFF_ID": build.diff_id,
                },
            )
            task_id = task["status"]["taskId"]
            logger.info("Triggered a new risk analysis task", id=task_id)

            # Send task to monitoring
            await self.bus.send(
                QUEUE_MONITORING_COMMUNITY,
                ("project-bugbug", "bugbug-classify-patch", task_id),
            )
        except Exception as e:
            logger.error("Failed to trigger risk analysis task", error=str(e))

    def should_run_test_selection(self, build):
        """
        Check if we should trigger a test selection for this revision:
        * randomly for a subset of revisions
        """
        if self.community_tc is None or not self.test_selection_enabled:
            return False

        return random.random() < self.test_selection_share

    async def start_test_selection(self, build: PhabricatorBuild, revision: str):
        """
        Run test selection by triggering a Taskcluster hook
        """
        assert build.state == PhabricatorBuildState.Public
        try:
            if not self.should_run_test_selection(build):
                return

            task = self.community_tc["hooks"].triggerHook(
                "project-bugbug",
                "bugbug-test-select",
                {
                    "PHABRICATOR_DEPLOYMENT": self.phabricator_deployment,
                    "DIFF_ID": build.diff_id,
                    "RUNNABLE_JOBS": self.index_service.buildUrl(
                        "findArtifactFromTask",
                        f"gecko.v2.try.revision.{revision}.firefox.decision",
                        "public/runnable-jobs.json",
                    ),
                },
            )
            task_id = task["status"]["taskId"]
            logger.info("Triggered a new test selection task", id=task_id)

            # Send task to monitoring
            await self.bus.send(
                QUEUE_MONITORING_COMMUNITY,
                ("project-bugbug", "bugbug-test-select", task_id),
            )
        except Exception as e:
            logger.error("Failed to trigger test selection task", error=str(e))

    async def get_test_selection_results(self, task_id):
        # Get the Phabricator diff ID from bugbug task definition.
        bugbug_task = self.community_tc["queue"].task(task_id)
        phabricator_deployment = str(bugbug_task["extra"]["phabricator-deployment"])
        diff_id = str(bugbug_task["extra"]["phabricator-diff-id"])

        if self.phabricator_deployment != phabricator_deployment:
            return (phabricator_deployment, diff_id, False, [])

        # Retrieve artifacts from bugbug test selection task.
        failure_risk = self.community_tc["queue"].getLatestArtifact(
            task_id, "public/failure_risk"
        )
        assert isinstance(failure_risk, int)

        if failure_risk == 0:
            return (phabricator_deployment, diff_id, False, [])

        selected_tasks = self.community_tc["queue"].getLatestArtifact(
            task_id, "public/selected_tasks"
        )

        return (phabricator_deployment, diff_id, True, selected_tasks)

    def add_new_jobs(self, revision, selected_tasks):
        selected_tasks = {"tasks": selected_tasks["response"].text.splitlines()}
        if len(selected_tasks["tasks"]) == 0:
            return None

        # Get the decision task of the push to try.
        decision_task_index = self.index_service.findTask(
            "gecko.v2.try.revision.{}.taskgraph.decision".format(revision)
        )
        decision_task_id = decision_task_index["taskId"]

        # Find the 'add-new-jobs' action to add new jobs to the task group.
        actions = self.queue_service.getLatestArtifact(
            decision_task_id, "public/actions.json"
        )
        add_job_action = next(
            action for action in actions["actions"] if action["name"] == "add-new-jobs"
        )
        assert add_job_action["kind"] == "hook"

        # Trigger the 'add-new-jobs' action with the list of tasks bugbug selected.
        jsonschema.validate(instance=selected_tasks, schema=add_job_action["schema"])

        hookPayload = jsone.render(
            add_job_action["hookPayload"],
            context={
                "taskId": None,
                "taskGroupId": decision_task_id,
                "input": selected_tasks,
            },
        )

        add_job_task = self.hooks_service.triggerHook(
            add_job_action["hookGroupId"], add_job_action["hookId"], hookPayload
        )
        add_job_task_id = add_job_task["status"]["taskId"]
        logger.info(
            "Triggered a add-new-jobs task to add a set of test tasks",
            task_group=decision_task_id,
            id=add_job_task_id,
        )

        return decision_task_id

    async def got_bugbug_test_select_end(self, payload):
        assert self.test_selection_enabled, "Test selection disabled"

        bugbug_task_id = payload["body"]["status"]["taskId"]

        try:
            (
                phabricator_deployment,
                diff_id,
                failure_risk,
                selected_tasks,
            ) = await self.get_test_selection_results(bugbug_task_id)
        except Exception as e:
            logger.error(
                "Failure getting test selection results from bugbug task",
                task=bugbug_task_id,
                error=e,
            )
            return

        # If this diff belongs to a Phabricator deployment we are not attached to, return.
        if self.phabricator_deployment != phabricator_deployment:
            return

        # If this diff does not belong to a revision we pushed to try, return.
        try:
            push = await self.diff_to_push.get(diff_id)
            asyncio.create_task(self.diff_to_push.rem(diff_id))
        except KeyError:
            logger.warning(
                "bugbug test select notification for a revision we did not push to try",
                payload=payload,
                diff_id=diff_id,
                bugbug_task_id=bugbug_task_id,
            )
            return

        # If the failure risk is low, don't trigger tests.
        if not failure_risk:
            return

        try:
            decision_task_id = self.add_new_jobs(push["revision"], selected_tasks)
        except Exception as e:
            logger.error(
                "Failure adding new jobs on try push",
                revision=push["revision"],
                diff=diff_id,
                error=e,
            )
            return

        if decision_task_id is None:
            return

        # Store the task group ID and a link to the Phabricator build, so we can upload
        # results to Phabricator when we get a task completion/failure notification.
        await self.task_group_to_push.set(decision_task_id, push)

        for email in self.test_selection_notify_addresses:
            await self.notify_service.email(
                {
                    "address": email,
                    "subject": "Test selection triggered for {}".format(
                        push["revision"]
                    ),
                    "content": push["treeherder_url"],
                    "template": "fullscreen",
                }
            )

    async def got_try_task_end(self, payload):
        assert self.test_selection_enabled, "Test selection disabled"

        try:
            body = payload["body"]
            task = body["task"]

            # source-test failures are reported by the bot.
            if (
                "kind" not in task["tags"]
                or task["tags"]["kind"] != "test"
                or "runId" not in body
            ):
                return

            status = body["status"]

            # We could get the build from a task ["extra"]["code-review"]["phabricator-diff"] to support
            # jobs added by humans too, but it would mean having to list the whole task group to find
            # a task with that key (or get it from try_task_config.json on the try repo, using the
            # revision from the decision task).
            taskGroupId = status["taskGroupId"]
            try:
                push = await self.task_group_to_push.get(taskGroupId)
                build = push["build"]
                revision = push["revision"]
            except KeyError:
                return

            name = task["tags"]["label"]

            treeherder_url = None

            state = status["state"]
            if state == "completed":
                result = UnitResultState.Pass
            elif state in ("failed", "exception"):
                result = UnitResultState.Fail

                treeherder_url = get_job_url(
                    "try", revision, status["taskId"], body["runId"]
                )

            else:
                logger.error("Unexpected state", state=state)
                return

            await self.bus.send(
                QUEUE_PHABRICATOR_RESULTS,
                (
                    "test_result",
                    build,
                    {"name": name, "result": result, "details": treeherder_url},
                ),
            )
        except Exception as e:
            logger.error(
                "Exception when parsing task ending payload", error=e, payload=payload
            )
