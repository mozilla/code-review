# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import base64
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from itertools import groupby

import structlog
from libmozdata.phabricator import BuildState, ConduitError, PhabricatorAPI
from taskcluster.utils import stringDate

from code_review_bot import Level, stats
from code_review_bot.analysis import (
    PhabricatorRevisionBuild,
    publish_analysis_lando,
    publish_analysis_phabricator,
)
from code_review_bot.backend import BackendAPI
from code_review_bot.config import settings
from code_review_bot.git import git_clone
from code_review_bot.mercurial import (
    MercurialRepository,
    MercurialWorker,
    robust_checkout,
)
from code_review_bot.report.debug import DebugReporter
from code_review_bot.revisions import GithubRevision, PhabricatorRevision, Revision
from code_review_bot.sources.phabricator import (
    PhabricatorActions,
    PhabricatorBuildState,
)
from code_review_bot.tasks.base import AnalysisTask, BaseTask, NoticeTask
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

DECISION_TASK_ROUTE = "gecko.v2.{repo}.revision.{revision}.taskgraph.decision"
PUBLICATION_LOG_ARTIFACT = "public/logs/live_backing.log"
TREEHERDER_LINK_REGEX = re.compile(
    rb"treeherder\.mozilla\.org/(?:#/)?jobs\?repo=(?P<repo>[\w-]+)"
    rb"&revision=(?P<revision>[0-9a-f]{12,40})"
)


class Workflow:
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

        # Is local clone already setup ?
        self.clone_available = False
        # Background clone in progress, see start_clone & clone_repository
        self.clone_executor = None
        self.clone_future = None

    def run(self, revision):
        """
        Find all issues on remote tasks and publish them
        """
        # Start cloning the local repo in the background ASAP
        # It is only awaited when the issues hashes are needed
        self.start_clone(revision)

        # Index ASAP Taskcluster task for this revision
        self.index(revision, state="started")

        # Set the Phabricator build as running
        self.update_status(revision, state=BuildState.Work)
        if settings.taskcluster_url and isinstance(revision, PhabricatorRevision):
            self.publish_link(
                revision,
                slug="publication",
                name="Publication task",
                url=settings.taskcluster_url,
            )

        # Analyze revision patch to get files/lines data
        revision.analyze_patch()

        # Find issues on remote tasks
        issues, task_failures, notices, reviewers = self.find_issues(
            revision, settings.try_group_id
        )

        # Analyze issues in case the before/after feature is enabled
        if revision.before_after_feature:
            logger.info("Running the before/after feature")
            # Search a base revision from the decision task
            decision = self.queue_service.task(settings.try_group_id)
            base_rev_changeset = (
                decision.get("payload", {}).get("env", {}).get("GECKO_BASE_REV")
            )
            if not base_rev_changeset:
                logger.warning(
                    "Base revision changeset could not be fetched from Phabricator, "
                    "looking for existing issues based on the current date",
                    task=settings.try_group_id,
                )

            # Clone local repo when required
            # as find_previous_issues will build the hashes
            self.clone_repository(revision)

            # Mark know issues to avoid publishing them on this patch
            self.find_previous_issues(revision, issues, base_rev_changeset)
            new_issues_count = sum(issue.new_issue for issue in issues)
            logger.info(
                f"Found {new_issues_count} new issues (over {len(issues)} total detected issues)",
                task=settings.try_group_id,
            )
        else:
            # Clone local repo when required
            # as publication need the hashes
            self.clone_repository(revision)

        if (
            all(issue.new_issue is False for issue in issues)
            and not task_failures
            and not notices
        ):
            logger.info("No issues nor notices, stopping there.")

        # Publish all issues
        self.publish(revision, issues, task_failures, notices, reviewers)

        return issues

    def ingest_revision(self, revision, group_id):
        """
        Simpler workflow to ingest a revision
        """
        if not isinstance(revision, PhabricatorRevision):
            raise NotImplementedError(
                "Only Phabricator revisions are supported for now"
            )
        assert (
            revision.from_autoland or revision.from_mozilla_central
        ), "Need a revision from autoland or mozilla-central"
        logger.info(
            "Starting revision ingestion",
            bugzilla=revision.bugzilla_id,
            title=revision.title,
            head_repository=revision.head_repository,
            head_changeset=revision.head_changeset,
        )

        assert (
            self.backend_api.enabled
        ), "Backend storage is disabled, revision ingestion is not possible"

        # Start cloning the local repo in the background ASAP
        # It is only awaited when the issues hashes are needed
        self.start_clone(revision)

        # Index ASAP Taskcluster task for this revision
        self.index(revision, state="ingestion")

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

                    # Log cleanly on autoland unknown tasks
                    if (
                        task is None
                        and revision.from_autoland
                        and task_name.startswith("source-test-")
                    ):
                        logger.info("Skipping unknown task", name=task_name)

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
                    f"Found {len(task_issues)} issues",
                    task=task.name,
                    id=task.id,
                )
                issues += task_issues

        # Store the revision & diff in the backend
        self.backend_api.publish_revision(revision)

        # Publish issues when there are some
        if not issues:
            logger.info("No issues for that revision")
            return

        # Clone local repo when required
        self.clone_repository(revision)

        # Publish issues in the backend
        self.backend_api.publish_issues(issues, revision)

    def start_analysis(self, revision):
        """
        Apply a patch on a local clone and push to try to trigger a new Code review analysis
        """
        logger.info("Starting revision analysis", revision=revision)
        if not isinstance(revision, PhabricatorRevision):
            raise NotImplementedError(
                "Only Phabricator revisions are supported for now"
            )

        # Index ASAP Taskcluster task for this revision
        self.index(revision, state="analysis")

        # Do not process revisions from black-listed users
        if revision.is_blacklisted:
            logger.warning("Blacklisted author, stopping there.")
            return

        # Cannot run without either mercurial or github cache configured
        if not settings.mercurial_cache and not settings.git_cache:
            raise Exception(
                "One of Mercurial cache or github cache must be configured to start analysis"
            )

        # Cannot run without ssh key
        if not settings.ssh_key:
            raise Exception("SSH Key must be configured to start analysis")

        # Set the Phabricator build as running
        self.update_status(revision, state=BuildState.Work)
        if settings.taskcluster_url and isinstance(revision, PhabricatorRevision):
            self.publish_link(
                revision,
                slug="analysis",
                name="Analysis task",
                url=settings.taskcluster_url,
            )

        # Initialize Phabricator build using revision
        build = PhabricatorRevisionBuild(revision, self.phabricator)

        # Copy internal Phabricator credentials to setup libmozevent
        phabricator = PhabricatorActions(
            url=self.phabricator.url,
            api_key=self.phabricator.api_key,
        )

        # Initialize mercurial repository
        repository = MercurialRepository(
            config={
                "name": revision.base_repository_conf.name,
                "try_name": revision.base_repository_conf.try_name,
                "url": revision.base_repository_conf.url,
                "try_url": revision.base_repository_conf.try_url,
                # Setup ssh identity
                "ssh_user": revision.base_repository_conf.ssh_user,
                "ssh_key": settings.ssh_key,
                # Force usage of robustcheckout
                "checkout": "robust",
            },
            cache_root=settings.mercurial_cache,
        )

        # Clone the required repository in the background
        # while waiting for the build to become public
        with ThreadPoolExecutor(max_workers=1) as executor:
            clone = executor.submit(repository.clone)

            # Try to update the state 5 consecutive time
            for i in range(5):
                # Update the internal build state using Phabricator infos
                phabricator.update_state(build)

                # Continue with workflow once the build is public
                if build.state is PhabricatorBuildState.Public:
                    break

                # Retry later if the build is not yet seen as public
                logger.warning(
                    "Build is not public, retrying in 30s",
                    build=build,
                    retries_left=build.retries,
                )
                time.sleep(30)

            # Wait for the clone to be finished, raising on failure
            clone.result()

        # Make sure the build is now public
        if build.state is not PhabricatorBuildState.Public:
            raise Exception("Cannot process private builds")

        # When the build is public, load patches from Phabricator
        if not build.stack:
            raise Exception("No stack of patches to apply.")

        # Apply the stack of patches and push to try
        worker = MercurialWorker()
        output = worker.run(repository, build)

        # Cancel any in-progress tasks from an earlier update
        # This is done after pushing to try to avoid delaying runs of the
        # new tasks.
        self.cancel_previous(revision)

        # Update index when the patch has been pushed to try
        self.index(revision, state="pushed_to_try")

        # Update final state using worker output
        if self.update_build and isinstance(revision, PhabricatorRevision):
            publish_analysis_phabricator(output, self.phabricator)
        else:
            logger.info("Skipping Phabricator publication")

        # Send Build in progress or errors to Lando
        lando_reporter = self.reporters.get("lando")
        if lando_reporter is not None:
            publish_analysis_lando(output, lando_reporter.lando_api)
        else:
            logger.info("Skipping Lando publication")

    def start_clone(self, revision):
        """
        Start cloning the repo locally in a background thread when configured
        Use clone_repository to wait for the clone to be available
        """
        if self.clone_available:
            logger.debug("Local clone already setup")
            return

        if self.clone_future is not None:
            logger.debug("Local clone already in progress")
            return

        if not settings.mercurial_cache and not settings.git_cache:
            logger.info("Local clone not required")
            return

        logger.info("Starting local clone in the background")
        self.clone_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="clone"
        )
        self.clone_future = self.clone_executor.submit(self._clone, revision)

    def clone_repository(self, revision):
        """
        Make sure the repo is cloned locally when configured
        Wait for a background clone started with start_clone, or run it now
        On production this should use a Taskcluster cache
        """
        if self.clone_available:
            logger.debug("Local clone already setup")
            return

        if self.clone_future is None:
            self.start_clone(revision)

        # Clone not required
        if self.clone_future is None:
            return

        logger.info("Waiting for local clone to be available")
        try:
            self.clone_future.result()
        finally:
            self.clone_future = None
            self.clone_executor.shutdown(wait=False)
            self.clone_executor = None

        self.clone_available = True

    def _clone(self, revision):
        """
        Effectively clone the repo locally
        """
        if isinstance(revision, PhabricatorRevision):
            # Mercurial clone
            if not settings.mercurial_cache:
                raise Exception(
                    "Mercurial cache directory is not configured, cannot clone"
                )
            logger.info(
                "Cloning mercurial revision to build issues",
                repo=revision.base_repository,
                changeset=revision.head_changeset,
                dest=settings.mercurial_cache_checkout,
            )
            robust_checkout(
                repo_upstream_url=revision.base_repository,
                repo_url=revision.head_repository,
                revision=revision.head_changeset,
                checkout_dir=settings.mercurial_cache_checkout,
                sharebase_dir=settings.mercurial_cache_sharebase,
            )
        elif isinstance(revision, GithubRevision):
            # Git clone
            if not settings.git_cache:
                raise Exception("Git cache directory is not configured, cannot clone")
            logger.info(
                "Cloning mercurial revision to build issues",
                repo=revision.base_repository,
                changeset=revision.head_changeset,
                dest=settings.git_cache,
            )
            git_clone(
                base_repository=revision.base_repository,
                head_repository=revision.head_repository,
                revision=revision.head_changeset,
                destination=settings.git_cache,
            )
        else:
            raise NotImplementedError

    def publish(self, revision, issues, task_failures, notices, reviewers):
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
                reporter.publish(issues, revision, task_failures, notices, reviewers)

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

    def cancel_previous(self, revision):
        """
        Cancel the code-review task, try pushes, and HarborMaster buildables of earlier
        updates of a revision.
        """

        # In order to cancel tasks from a previous push we need the task group id
        # that the tasks ran under (which is the same as the decision task for that push).
        # The only way to retrieve this through the Phabricator API is by a long series
        # of requests:
        # * Find all of the prior Build Targets (via builds, via buildables)
        # * Find the log for each Build Target, which will contain a taskId of Code Review task
        # * Pull the Code Review task log to fetch the treeherder link with the revision pushed to Try in it
        # * Look up the decision task id in the task index via the revision
        #
        # (Despite the fact that the Phabricator UI shows the treeherder link in it, this is
        #  not available through the API, so we have to take the long way to get here.)
        try:
            buildable_phids = self.list_previous_buildables(revision)
        except Exception as e:
            logger.warn(
                "Failed to find previous buildables",
                rev=str(revision),
                error=str(e),
            )
            return

        try:
            task_ids = self.find_previous_task_ids(revision, buildable_phids)
        except Exception as e:
            logger.warn(
                "Failed to find previous publication tasks",
                rev=str(revision),
                error=str(e),
            )
            task_ids = []

        for task_id in task_ids:
            # cancel the publication task, which may or may not be running still
            try:
                self.queue_service.cancelTask(task_id)
                logger.info("Cancelled a previous publication task", task=task_id)
            except Exception as e:
                logger.warn(
                    "Failed to cancel a previous publication task",
                    task=task_id,
                    error=str(e),
                )

            # No need to check whether or not anything is active in the group;
            # cancelling is idempotent.
            task_group_id = self.find_try_decision_task(task_id)
            if task_group_id is None:
                continue

            try:
                # task groups must be sealed before they can be cancelled
                self.queue_service.sealTaskGroup(task_group_id)
                self.queue_service.cancelTaskGroup(task_group_id)
            except Exception as e:
                logger.warn(
                    "Failed to cancel a previous try push",
                    task_group_id=task_group_id,
                    error=str(e),
                )
                continue

            logger.info("Cancelled a previous try push", task_group_id=task_group_id)

        for buildable_phid in buildable_phids:
            try:
                # This is safe to do even for completed buildables; the abort
                # requests will simply be ignored in this case.
                self.phabricator.request(
                    "harbormaster.sendmessage",
                    receiver=buildable_phid,
                    type="abort",
                )
            except Exception as e:
                logger.warn(
                    "Failed to abort a previous buildable",
                    buildable_phid=buildable_phid,
                    error=str(e),
                )
                continue

            logger.info(
                "Requested an abort of a previous buildable",
                buildable_phid=buildable_phid,
            )

    def list_previous_buildables(self, revision):
        """
        List the HarborMaster buildables of the previous updates of a revision

        Only the buildables of the diffs preceding the one being processed are
        returned. The buildable of the current diff is left out because aborting
        it would abort the build this very task is reporting to, and those of
        later diffs because they belong to updates that are themselves busy
        superseding this one.
        """
        logger.debug("Finding previous buildables", phid=revision.phabricator_phid)
        buildables = self.phabricator.request(
            "harbormaster.buildable.search",
            constraints={"containerPHIDs": [revision.phabricator_phid]},
        )["data"]

        diff_phids = {buildable["fields"]["objectPHID"] for buildable in buildables} - {
            revision.diff_phid
        }
        if not diff_phids:
            logger.debug("No previous buildables found", phid=revision.phabricator_phid)
            return []

        diff_ids = {
            diff["phid"]: diff["id"]
            for diff in self.phabricator.request(
                "differential.diff.search",
                constraints={"phids": sorted(diff_phids)},
            )["data"]
        }

        buildable_phids = []
        for buildable in buildables:
            diff_id = diff_ids.get(buildable["fields"]["objectPHID"])
            if diff_id is not None and diff_id < revision.diff_id:
                buildable_phids.append(buildable["phid"])

        if not buildable_phids:
            logger.debug("No previous buildables found", phid=revision.phabricator_phid)
            return []

        logger.debug(
            "Found buildables",
            phid=revision.phabricator_phid,
            buildables=buildable_phids,
        )
        return buildable_phids

    def find_previous_task_ids(self, revision, buildable_phids):
        """
        List the publication task ids found in the build logs of some buildables.
        """
        if not buildable_phids:
            return []

        builds = self.phabricator.request(
            "harbormaster.build.search",
            constraints={"buildables": buildable_phids},
        )["data"]
        if not builds:
            logger.debug("No builds found", buildables=buildable_phids)
            return []

        build_phids = [b["phid"] for b in builds]

        logger.debug("Found builds", buildables=buildable_phids, builds=build_phids)
        targets = self.phabricator.request(
            "harbormaster.target.search",
            constraints={"buildPHIDs": build_phids},
        )["data"]
        if not targets:
            return []

        build_target_phids = [target["phid"] for target in targets]

        logger.debug(
            "Found build targets", builds=build_phids, build_targets=build_target_phids
        )

        logs = self.phabricator.request(
            "harbormaster.log.search",
            constraints={"buildTargetPHIDs": build_target_phids},
        )["data"]

        task_ids = []
        for log in logs:
            phid = log["fields"]["filePHID"]
            logger.debug("Downloading log", file=phid)
            blob = self.phabricator.request("file.download", phid=phid)
            try:
                payload = json.loads(base64.b64decode(blob).decode("utf-8", "replace"))
            except (TypeError, ValueError):
                logger.debug("Couldn't parse log", file=phid)
                continue

            if not isinstance(payload, dict):
                logger.debug("Log is not an object", file=phid)
                continue

            task_id = payload.get("taskId")
            if not task_id:
                logger.debug("Couldn't find task id", file=phid)
                continue

            if task_id not in task_ids:
                task_ids.append(task_id)

        return task_ids

    def find_try_decision_task(self, publication_task_id):
        """
        Find the decision task of the try push made by a publication task

        The Treeherder link it published is only available in its own backing
        log, so this is only usable once that task has resolved.
        """
        url = self.queue_service.buildUrl(
            "getLatestArtifact", publication_task_id, PUBLICATION_LOG_ARTIFACT
        )
        # Allows HTTP_30x redirections retrieving the artifact
        response = self.queue_service.session.get(
            url, stream=True, allow_redirects=True
        )
        if not response.ok:
            logger.warn(
                "Failed to read the log of a publication task",
                task=publication_task_id,
                error=response.status_code,
            )
            return

        match = TREEHERDER_LINK_REGEX.search(response.content)
        if match is None:
            logger.info(
                "No try push found for a publication task", task=publication_task_id
            )
            return

        route = DECISION_TASK_ROUTE.format(
            repo=match.group("repo").decode("utf-8"),
            revision=match.group("revision").decode("utf-8"),
        )
        try:
            return self.index_service.findTask(route)["taskId"]
        except Exception as e:
            logger.warn("Failed to find a decision task", route=route, error=str(e))

    def index(self, revision, **kwargs):
        """
        Index current task on Taskcluster index
        """
        assert isinstance(revision, Revision), "Must be a Revision instance"

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

        # Add the repository we are working on for Phabricator revisions
        # This is mainly used by the frontend to list & filter diffs
        if isinstance(revision, PhabricatorRevision):
            payload["repository"] = revision.base_repository

        # Add restartable flag for monitoring
        payload["monitoring_restart"] = payload["state"] == "error" and payload.get(
            "error_code"
        ) in ("watchdog", "mercurial")

        # Add a sub namespace with the task id to be able to list
        # tasks from the parent namespace
        namespaces = revision.namespaces + [
            f"{namespace}.{settings.taskcluster.task_id}"
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

    def find_previous_issues(self, revision, issues, base_rev_changeset=None):
        """
        Look for known issues in the backend matching the given list of issues

        If a base revision ID is provided, compare to issues detected on this revision
        Otherwise, compare to issues detected on last ingested revision
        """
        assert (
            self.backend_api.enabled
        ), "Backend storage is disabled, comparing issues is not possible"

        current_date = datetime.now().strftime("%Y-%m-%d")

        # Group issues by path, so we only list know issues for the affected files
        issues_groups = groupby(
            sorted(issues, key=lambda i: i.path),
            lambda i: i.path,
        )
        logger.info(
            "Checking for existing issues in the backend",
            base_revision_changeset=base_rev_changeset,
        )

        if isinstance(revision, PhabricatorRevision):
            repository_slug = "mozilla-central"
        elif isinstance(revision, GithubRevision):
            # TODO: Rely on the central repository for known issues
            repository_slug = revision.repository_slug
        else:
            raise NotImplementedError

        for path, group_issues in issues_groups:
            known_issues = self.backend_api.list_repo_issues(
                repository_slug,
                date=current_date,
                revision_changeset=base_rev_changeset,
                path=path,
            )
            hashes = [issue["hash"] for issue in known_issues]
            for issue in group_issues:
                issue.new_issue = bool(issue.hash and issue.hash not in hashes)

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

        # Store the revision in the backend (or retrieve an existing one)
        rev = self.backend_api.publish_revision(revision)
        assert (
            rev is not None
        ), "Stopping early because revision could not be created nor retrieved from the backend"

        # Load task description
        task = tasks.get(settings.try_task_id)
        assert task is not None, f"Missing task {settings.try_task_id}"
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
                return [], [], [], []

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
                    task_issues, task_patches = [], []
                    if isinstance(task, AnalysisTask):
                        task_issues = task.parse_issues(artifacts, revision)
                        logger.info(
                            f"Found {len(task_issues)} issues",
                            task=task.name,
                            id=task.id,
                        )
                        stats.report_task(task, task_issues)
                        issues += task_issues

                        task_patches = task.build_patches(artifacts)
                        for patch in task_patches:
                            revision.add_improvement_patch(task, patch)

                    if isinstance(task, NoticeTask):
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

        reviewers = (
            task.extra_reviewers_groups if task and isinstance(task, BaseTask) else []
        )
        return issues, task_failures, notices, reviewers

    def build_task(self, task_status):
        """
        Create a specific implementation of AnalysisTask according to the task name
        """
        try:
            task_id = task_status["status"]["taskId"]
        except KeyError:
            raise Exception(f"Cannot read task name {task_id}")
        try:
            name = task_status["task"]["metadata"]["name"]
        except KeyError:
            raise Exception(f"Cannot read task name {task_id}")

        # Specific tasks detections are enabled first, default format is used as a fallback
        if name.startswith("source-test-mozlint-"):
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
        elif DefaultTask.matches(task_id):
            return DefaultTask(task_id, task_status)

    def update_status(self, revision, state):
        """
        Update build status on HarborMaster
        """
        if isinstance(revision, GithubRevision):
            logger.warning("No Lando publication for Github yet")
            return

        assert isinstance(state, BuildState)

        # Skip github status update, as we rely on the github reporter for publication
        if isinstance(revision, GithubRevision):
            return

        if not revision.build_target_phid:
            logger.info(
                "No build target found, skipping HarborMaster update", state=state.value
            )
            return

        if not self.update_build or not isinstance(revision, PhabricatorRevision):
            logger.info(
                "Update build disabled, skipping HarborMaster update", state=state.value
            )
            return

        self.phabricator.update_build_target(revision.build_target_phid, state)
        logger.info("Updated HarborMaster status", state=state, revision=revision)

    def publish_link(self, revision: Revision, slug: str, name: str, url: str):
        """
        Publish a link as a HarborMaster artifact
        """
        if not isinstance(revision, PhabricatorRevision):
            raise NotImplementedError(
                "Only Phabricator revisions are supported for now"
            )

        if not revision.build_target_phid:
            logger.info(
                "No build target found, skipping HarborMaster link creation",
                slug=slug,
                url=url,
            )
            return

        if not self.update_build:
            logger.info(
                "Update build disabled, skipping HarborMaster link creation",
                slug=slug,
                url=url,
            )
            return

        try:
            self.phabricator.create_harbormaster_uri(
                revision.build_target_phid, slug, name, url
            )
        except ConduitError as e:
            if e.error_info and "Duplicate entry" in e.error_info:
                logger.warning(
                    "Harbormaster URI artifact already exists, skipping creation (retry?)",
                    slug=slug,
                    url=url,
                )
            else:
                logger.warn(
                    "Failed to publish a URI on harbormaster",
                    build=revision.build_target_phid,
                    slug=slug,
                    name=name,
                    url=url,
                    error=str(e),
                )
                raise
