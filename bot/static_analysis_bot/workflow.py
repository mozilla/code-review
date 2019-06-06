# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import datetime
from datetime import timedelta

import structlog
from libmozdata.phabricator import BuildState
from libmozdata.phabricator import PhabricatorAPI

from static_analysis_bot import stats
from static_analysis_bot.config import settings
from static_analysis_bot.report.debug import DebugReporter
from static_analysis_bot.revisions import Revision
from static_analysis_bot.tasks.base import AnalysisTask
from static_analysis_bot.tasks.clang_format import ClangFormatTask
from static_analysis_bot.tasks.clang_tidy import ClangTidyTask
from static_analysis_bot.tasks.coverage import ZeroCoverageTask
from static_analysis_bot.tasks.coverity import CoverityTask
from static_analysis_bot.tasks.infer import InferTask
from static_analysis_bot.tasks.lint import MozLintTask
from static_analysis_bot.tools.taskcluster import TASKCLUSTER_DATE_FORMAT

logger = structlog.get_logger(__name__)

TASKCLUSTER_NAMESPACE = 'project.releng.services.project.{channel}.static_analysis_bot.{name}'
TASKCLUSTER_INDEX_TTL = 7  # in days


class Workflow(object):
    '''
    Full static analysis workflow
    - setup remote analysis workflow
    - find issues from remote tasks
    - publish issues
    '''
    def __init__(self, reporters, index_service, queue_service, phabricator_api, zero_coverage_enabled=True):
        assert settings.try_task_id is not None, \
            'Cannot run without Try task id'
        assert settings.try_group_id is not None, \
            'Cannot run without Try task id'
        self.zero_coverage_enabled = zero_coverage_enabled

        # Use share phabricator API client
        assert isinstance(phabricator_api, PhabricatorAPI)
        self.phabricator = phabricator_api

        # Load reporters to use
        self.reporters = reporters
        if not self.reporters:
            logger.warn('No reporters configured, this analysis will not be published')

        # Always add debug reporter and Diff reporter
        self.reporters['debug'] = DebugReporter(output_dir=settings.taskcluster.results_dir)

        # Use TC services client
        self.index_service = index_service
        self.queue_service = queue_service

    def run(self, revision):
        '''
        Find all issues on remote tasks and publish them
        '''
        # Index ASAP Taskcluster task for this revision
        self.index(revision, state='started')

        # Set the Phabricator build as running
        revision.update_status(state=BuildState.Work)

        # Analyze revision patch to get files/lines data
        revision.analyze_patch()

        # Find issues on remote tasks
        issues = self.find_issues(revision)
        if not issues:
            logger.info('No issues, stopping there.')
            self.index(revision, state='done', issues=0)
            revision.update_status(BuildState.Pass)
            return []

        # Publish all issues
        self.publish(revision, issues)

        return issues

    def publish(self, revision, issues):
        '''
        Publish issues on selected reporters
        '''
        # Publish patches on Taskcluster
        # or write locally for local development
        for patch in revision.improvement_patches:
            if settings.taskcluster.local:
                patch.write()
            else:
                patch.publish(self.queue_service)

        # Report issues publication stats
        nb_issues = len(issues)
        nb_publishable = len([i for i in issues if i.is_publishable()])
        self.index(revision, state='analyzed', issues=nb_issues, issues_publishable=nb_publishable)
        stats.api.increment('analysis.issues.publishable', nb_publishable)

        # Publish reports about these issues
        with stats.api.timer('runtime.reports'):
            for reporter in self.reporters.values():
                reporter.publish(issues, revision)

        self.index(revision, state='done', issues=nb_issues, issues_publishable=nb_publishable)

        # Publish final HarborMaster state
        revision.update_status(nb_publishable > 0 and BuildState.Fail or BuildState.Pass)

    def index(self, revision, **kwargs):
        '''
        Index current task on Taskcluster index
        '''
        assert isinstance(revision, Revision)

        if settings.taskcluster.local or self.index_service is None:
            logger.info('Skipping taskcluster indexing', rev=str(revision), **kwargs)
            return

        # Build payload
        payload = revision.as_dict()
        payload.update(kwargs)

        # Always add the indexing
        now = datetime.utcnow()
        payload['indexed'] = now.strftime(TASKCLUSTER_DATE_FORMAT)

        # Always add the source and try config
        payload['source'] = 'try'
        payload['try_task_id'] = settings.try_task_id
        payload['try_group_id'] = settings.try_group_id

        # Add restartable flag for monitoring
        payload['monitoring_restart'] = payload['state'] == 'error' and \
            payload.get('error_code') in ('watchdog', 'mercurial')

        # Add a sub namespace with the task id to be able to list
        # tasks from the parent namespace
        namespaces = revision.namespaces + [
            '{}.{}'.format(namespace, settings.taskcluster.task_id)
            for namespace in revision.namespaces
        ]

        # Build complete namespaces list, with monitoring update
        full_namespaces = [
            TASKCLUSTER_NAMESPACE.format(channel=settings.app_channel, name=name)
            for name in namespaces
        ]
        full_namespaces.append('project.releng.services.tasks.{}'.format(settings.taskcluster.task_id))

        # Index for all required namespaces
        for namespace in full_namespaces:
            self.index_service.insertTask(
                namespace,
                {
                    'taskId': settings.taskcluster.task_id,
                    'rank': 0,
                    'data': payload,
                    'expires': (now + timedelta(days=TASKCLUSTER_INDEX_TTL)).strftime(TASKCLUSTER_DATE_FORMAT),
                }
            )

    def find_issues(self, revision):
        '''
        Find all issues on remote Taskcluster task group
        '''
        # Load all tasks in task group
        tasks = self.queue_service.listTaskGroup(settings.try_group_id)
        assert 'tasks' in tasks
        tasks = {
            task['status']['taskId']: task
            for task in tasks['tasks']
        }
        assert len(tasks) > 0
        logger.info('Loaded Taskcluster group', id=settings.try_group_id, tasks=len(tasks))

        # Update the local revision with tasks
        revision.setup_try(tasks)

        # Load task description
        task = tasks.get(settings.try_task_id)
        assert task is not None, 'Missing task {}'.format(settings.try_task_id)
        dependencies = task['task']['dependencies']
        assert len(dependencies) > 0, 'No task dependencies to analyze'

        # Skip dependencies not in group
        # But log all skipped tasks
        def _in_group(dep_id):
            if dep_id not in tasks:
                # Used for docker images produced in tree
                # and other artifacts
                logger.info('Skip dependency not in group', task_id=dep_id)
                return False
            return True
        dependencies = [
            dep_id
            for dep_id in dependencies
            if _in_group(dep_id)
        ]

        # Do not run parsers when we only have a gecko decision task
        # That means no analyzer were triggered by the taskgraph decision task
        # This can happen if the patch only touches file types for which we have no analyzer defined
        # See issue https://github.com/mozilla/release-services/issues/2055
        if len(dependencies) == 1:
            task = tasks[dependencies[0]]
            if task['task']['metadata']['name'] == 'Gecko Decision Task':
                logger.warn('Only dependency is a Decision Task, skipping analysis')
                return []

        # Add zero-coverage task
        if self.zero_coverage_enabled:
            dependencies.append(ZeroCoverageTask)

        # Find issues and patches in dependencies
        issues = []
        for dep in dependencies:
            try:
                if isinstance(dep, type) and issubclass(dep, AnalysisTask):
                    # Build a class instance from its definition and route
                    task = dep.build_from_route(self.index_service, self.queue_service)
                    if task is None:
                        continue
                else:
                    # Use a task from its id & description
                    task = self.build_task(dep, tasks[dep])
                artifacts = task.load_artifacts(self.queue_service)
                if artifacts is not None:
                    task_issues = task.parse_issues(artifacts, revision)
                    logger.info('Found {} issues'.format(len(task_issues)), task=task.name, id=task.id)
                    issues += task_issues

                    for name, patch in task.build_patches(artifacts):
                        revision.add_improvement_patch(name, patch)
            except Exception as e:
                logger.warn('Failure during task analysis', task=settings.taskcluster.task_id, error=e)
                raise

        return issues

    def build_task(self, task_id, task_status):
        '''
        Create a specific implemenation of AnalysisTask according to the task name
        '''
        try:
            name = task_status['task']['metadata']['name']
        except KeyError:
            raise Exception('Cannot read task name {}'.format(task_id))

        if name.startswith('source-test-mozlint-'):
            return MozLintTask(task_id, task_status)
        elif name == 'source-test-clang-tidy':
            return ClangTidyTask(task_id, task_status)
        elif name == 'source-test-clang-format':
            return ClangFormatTask(task_id, task_status)
        elif name == 'source-test-coverity-coverity':
            return CoverityTask(task_id, task_status)
        elif name == 'source-test-infer-infer':
            return InferTask(task_id, task_status)
        else:
            raise Exception('Unsupported task {}'.format(name))
