# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
from datetime import datetime
from datetime import timedelta

from cli_common.log import get_logger
from cli_common.phabricator import BuildState
from cli_common.phabricator import PhabricatorAPI
from cli_common.taskcluster import TASKCLUSTER_DATE_FORMAT
from static_analysis_bot import stats
from static_analysis_bot.config import SOURCE_TRY
from static_analysis_bot.config import settings
from static_analysis_bot.report.debug import DebugReporter
from static_analysis_bot.revisions import Revision
from static_analysis_bot.workflows.local import LocalWorkflow
from static_analysis_bot.workflows.remote import RemoteWorkflow

logger = get_logger(__name__)

TASKCLUSTER_NAMESPACE = 'project.releng.services.project.{channel}.static_analysis_bot.{name}'
TASKCLUSTER_INDEX_TTL = 7  # in days


class Workflow(object):
    '''
    Full static analysis workflow
    - setup local and remote analysis workflows
    - runs them to build issues
    - publish issues
    '''
    def __init__(self, reporters, analyzers, index_service, queue_service, phabricator_api):
        assert isinstance(analyzers, list)
        assert len(analyzers) > 0, \
            'No analyzers specified, will not run.'
        self.analyzers = analyzers
        assert 'MOZCONFIG' in os.environ, \
            'Missing MOZCONFIG in environment'

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

        # Build analysis workflows to run
        self.workflows = []

    def run(self, revision):
        '''
        Build analysis workflows and directly run them
        '''
        issues = []

        # Index ASAP Taskcluster task for this revision
        self.index(revision, state='started')

        # Set the Phabricator build as running
        revision.update_status(state=BuildState.Work)

        # Use remote when we are on try
        if settings.source == SOURCE_TRY:
            remote = RemoteWorkflow(self.queue_service)
            issues += remote.run(revision)

        # Always use local workflow
        # until we have all analyzers in-tree
        local = LocalWorkflow(self, self.analyzers, self.index_service)
        issues += local.run(revision)

        if not issues:
            logger.info('No issues, stopping there.')
            self.index(revision, state='done', issues=0)
            revision.update_status(BuildState.Pass)
            return

        # Publish all issues from both workflows at once
        self.publish(revision, issues)

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
        payload['source'] = settings.source
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
