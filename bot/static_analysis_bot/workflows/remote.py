# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from cli_common.log import get_logger
from static_analysis_bot.config import SOURCE_TRY
from static_analysis_bot.config import settings
from static_analysis_bot.lint import MozLintIssue

logger = get_logger(__name__)


ISSUE_MARKER = 'TEST-UNEXPECTED-ERROR | '


class AnalysisTask(object):
    '''
    An analysis CI task running on Taskcluster
    '''
    def __init__(self, task_id):
        self.task_id = task_id
        self.run_id = None
        self.task = None

    def load_logs(self, queue_service):

        # Load base task
        self.task = queue_service.task(self.task_id)
        self.name = self.task['metadata'].get('name', 'unknown')
        logger.info('Lookup task dependency', id=self.task_id, name=self.name)

        # Load task status
        status = queue_service.status(self.task_id)
        assert 'status' in status, 'No status data for {}'.format(self.task_id)
        state = status['status']['state']

        # Process only the failed tasks
        # A completed task here means the analyzer did not find any issues
        if state == 'completed':
            logger.info('No issues detected by completed task', id=self.task_id)
            return
        elif state != 'failed':
            logger.warn('Unsupported task state', state=state, id=self.task_id)
            return

        # Load artifact logs from the last run
        self.run_id = status['status']['runs'][-1]['runId']
        artifacts = queue_service.listArtifacts(self.task_id, self.run_id)
        assert 'artifacts' in artifacts, 'Missing artifacts'
        logs = [
            artifact['name']
            for artifact in artifacts['artifacts']
            if artifact['storageType'] != 'reference' and artifact['contentType'].startswith('text/')
        ]

        # Load logs from artifact API
        out = {}
        for log in logs:
            logger.info('Reading log', task_id=self.task_id, log=log)
            try:
                artifact = queue_service.getArtifact(self.task_id, self.run_id, log)
                assert 'response' in artifact, 'Failed loading artifact'
                out[log] = artifact['response'].content
            except Exception as e:
                logger.warn('Failed to read log', task_id=self.task_id, run_id=self.run_id, log=log, error=e)
                raise
        return out


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

        # Load task description
        task = self.queue_service.task(settings.try_task_id)
        assert len(task['dependencies']) > 0, 'No task dependencies to analyze'

        # Find issues in dependencies
        issues = []
        for dep_id in task['dependencies']:
            try:
                task = AnalysisTask(dep_id)
                logs = task.load_logs(self.queue_service)
                if logs is None:
                    continue

                for log in logs.values():
                    issues += self.parse_issues(task, log, revision)
            except Exception as e:
                logger.warn('Failure during task analysis', task=settings.taskcluster.task_id, error=e)
                raise
                continue

        return issues

    def parse_issues(self, task, log_content, revision):
        '''
        Parse issues from a log file content
        '''
        assert isinstance(task, AnalysisTask)

        # Lookup issues using marker
        issues = [
            line[line.index(ISSUE_MARKER) + len(ISSUE_MARKER):]
            for line in log_content.decode('utf-8').splitlines()
            if ISSUE_MARKER in line
        ]
        assert len(issues) > 0, 'No issues found in failure log'

        # Convert to Issue instances
        logger.info('Found {} issues !'.format(len(issues)))
        return list(filter(None, [
            self.build_issue(task.name, issue, revision)
            for issue in issues
        ]))

    def build_issue(self, task_name, issue, revision):
        '''
        Convert a raw text issue into an Issue instance
        TODO: this should be simplified by using mach JSON output
        '''
        if task_name.startswith(MozLintIssue.TRY_PREFIX):
            return MozLintIssue.from_try(task_name, issue, revision)
        else:
            logger.warn('Unsupported task type', name=task_name)
