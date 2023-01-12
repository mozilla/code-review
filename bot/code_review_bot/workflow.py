# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import datetime
from datetime import timedelta

import structlog
from libmozdata.phabricator import BuildState
from libmozdata.phabricator import PhabricatorAPI
from taskcluster.utils import stringDate

from code_review_bot import Level
from code_review_bot import stats
from code_review_bot.backend import BackendAPI
from code_review_bot.config import REPO_AUTOLAND
from code_review_bot.config import REPO_MOZILLA_CENTRAL
from code_review_bot.config import settings
from code_review_bot.report.debug import DebugReporter
from code_review_bot.revisions import Revision
from code_review_bot.tasks.base import AnalysisTask
from code_review_bot.tasks.base import NoticeTask
from code_review_bot.tasks.clang_format import ClangFormatTask
from code_review_bot.tasks.clang_tidy import ClangTidyTask
from code_review_bot.tasks.clang_tidy_external import ExternalTidyTask
from code_review_bot.tasks.coverage import ZeroCoverageTask
from code_review_bot.tasks.default import DefaultTask
from code_review_bot.tasks.docupload import DocUploadTask
from code_review_bot.tasks.lint import MozLintTask
from code_review_bot.tasks.tgdiff import TaskGraphDiffTask

logger = structlog.get_logger(__name__)

TASKCLUSTER_NAMESPACE = "project.relman.{channel}.code-review.{name}"
TASKCLUSTER_INDEX_TTL = 7  # in days


class Workflow(object):
    """
    Full static analysis workflow
    - setup remote analysis workflow
    - find issues from remote tasks
    - publish issues
    """

    def __init__(
        self,
        reporters,
        index_service,
        queue_service,
        phabricator_api,
        zero_coverage_enabled=True,
        update_build=True,
        task_failures_ignored=[],
        mercurial_repository=None,
    ):
        self.zero_coverage_enabled = zero_coverage_enabled
        self.update_build = update_build
        self.task_failures_ignored = task_failures_ignored
        logger.info("Will ignore task failures", names=self.task_failures_ignored)

        # Use share phabricator API client
        assert isinstance(phabricator_api, PhabricatorAPI)
        self.phabricator = phabricator_api

        # Load reporters to use
        self.reporters = reporters
        if not self.reporters:
            logger.warn("No reporters configured, this analysis will not be published")

        # Always add debug reporter and Diff reporter
        self.reporters["debug"] = DebugReporter(
            output_dir=settings.taskcluster.results_dir
        )

        # Use TC services client
        self.index_service = index_service
        self.queue_service = queue_service

        # Setup Backend API client
        self.backend_api = BackendAPI()

        # Path to the mercurial repository
        self.mercurial_repository = mercurial_repository

    def run(self, revision):
        """
        Find all issues on remote tasks and publish them
        """
        # Index ASAP Taskcluster task for this revision
        self.index(revision, state="started")

        # Set the Phabricator build as running
        self.update_status(revision, state=BuildState.Work)

        # Analyze revision patch to get files/lines data
        revision.analyze_patch()

        # Find issues on remote tasks
        issues, task_failures, notices = self.find_issues(
            revision, settings.try_group_id
        )
        if not issues and not task_failures and not notices:
            logger.info("No issues or notices, stopping there.")

        # Publish all issues
        self.publish(revision, issues, task_failures, notices)

        return issues

    def ingest_revision(self, revision, group_id):
        """
        Simpler workflow to ingest a revision
        """
        assert revision.repository in (
            REPO_AUTOLAND,
            REPO_MOZILLA_CENTRAL,
        ), "Need a revision from autoland or mozilla-central"
        logger.info(
            "Starting revision ingestion",
            revision=revision.id,
            bugzilla=revision.bugzilla_id,
            title=revision.title,
            mercurial_revision=revision.mercurial_revision,
        )

        assert (
            self.backend_api.enabled
        ), "Backend storage is disabled, revision ingestion is not possible"

        supported_tasks = []

        def _build_tasks(tasks):
            for task_status in tasks["tasks"]:
                try:
                    task_name = task_status["task"]["metadata"]["name"]
                    # Only analyze tasks stating with `source-test-` to avoid checking artifacts every time
                    if not task_name.startswith("source-test-"):
                        logger.debug(
                            f"Task with name '{task_name}' is not supported during the ingestion of a revision"
                        )
                        continue
                    task = self.build_task(task_status)
                except Exception as e:
                    logger.warning(f"Could not proceed task {task_name}: {e}")
                    continue
                if task is None or getattr(task, "parse_issues", None) is None:
                    # Do ignore tasks that cannot be parsed as issues
                    continue
                supported_tasks.append(task)

        # Find potential issues in the task group
        self.queue_service.listTaskGroup(group_id, paginationHandler=_build_tasks)
        logger.info(
            "Loaded all supported tasks in the task group",
            group_id=group_id,
            nb=len(supported_tasks),
        )

        # Load all the artifacts and potential issues
        issues = []
        for task in supported_tasks:
            artifacts = task.load_artifacts(self.queue_service)
            if artifacts is not None:
                task_issues = task.parse_issues(artifacts, revision)
                logger.info(
                    "Found {} issues".format(len(task_issues)),
                    task=task.name,
                    id=task.id,
                )
                issues += task_issues

        # Store the revision & diff in the backend
        self.backend_api.publish_revision(revision)

        # Publish issues when there are some
        if issues:
            if self.mercurial_repository:
                logger.info("Using the local repository to build issues")
            self.backend_api.publish_issues(
                issues,
                revision,
                mercurial_repository=self.mercurial_repository,
                bulk=100,
            )
        else:
            logger.info("No issues for that revision")

    def publish(self, revision, issues, task_failures, notices):
        """
        Publish issues on selected reporters
        """
        # Publish patches on Taskcluster
        # or write locally for local development
        for patch in revision.improvement_patches:
            if settings.taskcluster.local:
                patch.write()
            else:
                patch.publish()

        # Publish issues on backend to retrieve their comparison state
        # Only publish errors and "in patch" warnings due to a backend timeout
        publishable_issues = [i for i in issues if i.is_publishable()]

        self.backend_api.publish_issues(publishable_issues, revision)

        # Report issues publication stats
        nb_issues = len(issues)
        nb_publishable = len(publishable_issues)
        nb_publishable_errors = len(
            [i for i in publishable_issues if i.level == Level.Error]
        )

        self.index(
            revision,
            state="analyzed",
            issues=nb_issues,
            issues_publishable=nb_publishable,
        )
        stats.add_metric("analysis.issues.publishable", nb_publishable)

        # Publish reports about these issues
        with stats.timer("runtime.reports"):
            for reporter in self.reporters.values():
                reporter.publish(issues, revision, task_failures, notices)

        self.index(
            revision, state="done", issues=nb_issues, issues_publishable=nb_publishable
        )

        # Publish final HarborMaster state
        self.update_status(
            revision,
            BuildState.Fail
            if nb_publishable_errors > 0 or task_failures
            else BuildState.Pass,
        )

    def index(self, revision, **kwargs):
        """
        Index current task on Taskcluster index
        """
        assert isinstance(revision, Revision)

        if settings.taskcluster.local or self.index_service is None:
            logger.info("Skipping taskcluster indexing", rev=str(revision), **kwargs)
            return

        # Build payload
        payload = revision.as_dict()
        payload.update(kwargs)

        # Always add the indexing
        now = datetime.utcnow()
        payload["indexed"] = stringDate(now)

        # Always add the source and try config
        payload["source"] = "try"
        payload["try_task_id"] = settings.try_task_id
        payload["try_group_id"] = settings.try_group_id

        # Always add the repository we are working on
        # This is mainly used by the frontend to list & filter diffs
        payload["repository"] = revision.target_repository

        # Add restartable flag for monitoring
        payload["monitoring_restart"] = payload["state"] == "error" and payload.get(
            "error_code"
        ) in ("watchdog", "mercurial")

        # Add a sub namespace with the task id to be able to list
        # tasks from the parent namespace
        namespaces = revision.namespaces + [
            "{}.{}".format(namespace, settings.taskcluster.task_id)
            for namespace in revision.namespaces
        ]

        # Build complete namespaces list, with monitoring update
        full_namespaces = [
            TASKCLUSTER_NAMESPACE.format(channel=settings.app_channel, name=name)
            for name in namespaces
        ]

        # Index for all required namespaces
        for namespace in full_namespaces:
            self.index_service.insertTask(
                namespace,
                {
                    "taskId": settings.taskcluster.task_id,
                    "rank": 0,
                    "data": payload,
                    "expires": stringDate(now + timedelta(days=TASKCLUSTER_INDEX_TTL)),
                },
            )

    def find_issues(self, revision, group_id):
        """
        Find all issues on remote Taskcluster task group
        """
        # Load all tasks in task group
        tasks = self.queue_service.listTaskGroup(group_id)
        assert "tasks" in tasks
        tasks = {task["status"]["taskId"]: task for task in tasks["tasks"]}
        assert len(tasks) > 0
        logger.info("Loaded Taskcluster group", id=group_id, tasks=len(tasks))

        # Update the local revision with tasks
        revision.setup_try(group_id, tasks)

        # Store the revision in the backend
        # It needs to be after setup_try to have a repository value
        self.backend_api.publish_revision(revision)

        # Load task description
        task = tasks.get(settings.try_task_id)
        assert task is not None, "Missing task {}".format(settings.try_task_id)
        dependencies = task["task"]["dependencies"]
        assert len(dependencies) > 0, "No task dependencies to analyze"

        # Skip dependencies not in group
        # But log all skipped tasks
        def _in_group(dep_id):
            if dep_id not in tasks:
                # Used for docker images produced in tree
                # and other artifacts
                logger.info("Skip dependency not in group", task_id=dep_id)
                return False
            return True

        dependencies = [dep_id for dep_id in dependencies if _in_group(dep_id)]

        # Do not run parsers when we only have a gecko decision task
        # That means no analyzer were triggered by the taskgraph decision task
        # This can happen if the patch only touches file types for which we have no analyzer defined
        # See issue https://github.com/mozilla/release-services/issues/2055
        if len(dependencies) == 1:
            task = tasks[dependencies[0]]
            if task["task"]["metadata"]["name"] == "Gecko Decision Task":
                logger.warn("Only dependency is a Decision Task, skipping analysis")
                return [], [], []

        # Add zero-coverage task
        if self.zero_coverage_enabled:
            dependencies.append(ZeroCoverageTask)

        # Find issues and patches in dependencies
        issues = []
        task_failures = []
        notices = []
        for dep in dependencies:
            try:
                if isinstance(dep, type) and issubclass(dep, AnalysisTask):
                    # Build a class instance from its definition and route
                    task = dep.build_from_route(self.index_service, self.queue_service)
                else:
                    # Use a task from its id & description
                    task = self.build_task(tasks[dep])
                if task is None:
                    continue
                artifacts = task.load_artifacts(self.queue_service)
                if artifacts is not None:
                    if isinstance(task, AnalysisTask):
                        task_issues = task.parse_issues(artifacts, revision)
                        logger.info(
                            "Found {} issues".format(len(task_issues)),
                            task=task.name,
                            id=task.id,
                        )
                        stats.report_task(task, task_issues)
                        issues += task_issues

                        task_patches = task.build_patches(artifacts)
                        for patch in task_patches:
                            revision.add_improvement_patch(task, patch)

                    elif isinstance(task, NoticeTask):
                        notice = task.build_notice(artifacts, revision)
                        if notice:
                            notices.append(notice)

                    # Report a problem when tasks in erroneous state are found
                    # but no issue or patch has been processed by the bot
                    if task.state == "failed" and not task_issues and not task_patches:

                        # Skip task that are listed as ignorable (we try to avoid unnecessary spam)
                        if task.name in self.task_failures_ignored:
                            logger.warning(
                                "Ignoring task failure as configured",
                                task=task.name,
                                id=task.id,
                            )
                            continue

                        logger.warning(
                            "An erroneous task processed some artifacts and found no issues or patches",
                            task=task.name,
                            id=task.id,
                        )
                        task_failures.append(task)
            except Exception as e:
                logger.warn(
                    "Failure during task analysis",
                    task=settings.taskcluster.task_id,
                    error=e,
                )
                raise

        return issues, task_failures, notices

    def build_task(self, task_status):
        """
        Create a specific implementation of AnalysisTask according to the task name
        """
        try:
            task_id = task_status["status"]["taskId"]
        except KeyError:
            raise Exception("Cannot read task name {}".format(task_id))
        try:
            name = task_status["task"]["metadata"]["name"]
        except KeyError:
            raise Exception("Cannot read task name {}".format(task_id))

        # Default format is used first when the correct artifact is available
        if DefaultTask.matches(task_id):
            return DefaultTask(task_id, task_status)
        elif name.startswith("source-test-mozlint-"):
            return MozLintTask(task_id, task_status)
        elif name == "source-test-clang-tidy":
            return ClangTidyTask(task_id, task_status)
        elif name == "source-test-clang-format":
            return ClangFormatTask(task_id, task_status)
        elif name == "source-test-doc-upload":
            return DocUploadTask(task_id, task_status)
        elif name == "source-test-clang-external":
            return ExternalTidyTask(task_id, task_status)
        elif name == "source-test-taskgraph-diff":
            return TaskGraphDiffTask(task_id, task_status)
        elif settings.autoland_group_id is not None and not name.startswith(
            "source-test-"
        ):
            # Log cleanly on autoland unknown tasks
            logger.info("Skipping unknown task", id=task_id, name=name)
        else:
            return DefaultTask(task_id, task_status)

    def update_status(self, revision, state):
        """
        Update build status on HarborMaster
        """
        assert isinstance(state, BuildState)
        if not revision.build_target_phid:
            logger.info(
                "No build target found, skipping HarborMaster update", state=state.value
            )
            return

        if not self.update_build:
            logger.info(
                "Update build disabled, skipping HarborMaster update", state=state.value
            )
            return

        self.phabricator.update_build_target(revision.build_target_phid, state)
        logger.info("Updated HarborMaster status", state=state, revision=revision)
