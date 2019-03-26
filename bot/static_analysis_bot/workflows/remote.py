# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from cli_common.log import get_logger
from static_analysis_bot.clang.format import ClangFormatTask
from static_analysis_bot.clang.tidy import ClangTidyTask
from static_analysis_bot.config import SOURCE_TRY
from static_analysis_bot.config import settings
from static_analysis_bot.lint import MozLintTask

logger = get_logger(__name__)


class RemoteWorkflow(object):
    '''
    Secondary workflow to analyze the output from a try task group
    '''
    def __init__(self, queue_service):
        # Use TC services client
        self.queue_service = queue_service

    def run(self, revision):
        assert settings.source == SOURCE_TRY, \
            'Cannot run without Try source'
        assert settings.try_task_id is not None, \
            'Cannot run without Try task id'
        assert settings.try_group_id is not None, \
            'Cannot run without Try task id'

        # Analyze revision patch to get files/lines data
        revision.analyze_patch()

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

        # Find issues in dependencies
        issues = []
        for dep_id in dependencies:
            if dep_id not in tasks:
                # Used for docker images produced in tree
                # and other artifacts
                logger.info('Skip dependency not in group', task_id=dep_id)
                continue
            try:
                task = self.build_task(dep_id, tasks[dep_id])
                artifacts = task.load_artifacts(self.queue_service)
                if artifacts is not None:
                    task_issues = task.parse_issues(artifacts, revision)
                    logger.info('Found {} issues'.format(len(task_issues)), task=task.name, id=task.id)
                    issues += task_issues
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
        else:
            raise Exception('Unsupported task {}'.format(name))
