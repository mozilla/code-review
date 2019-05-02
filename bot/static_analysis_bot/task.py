# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from cli_common.log import get_logger

logger = get_logger(__name__)

WORKER_CHECKOUT = '/builds/worker/checkouts/gecko'


class AnalysisTask(object):
    '''
    An analysis CI task running on Taskcluster
    '''
    artifacts = []
    valid_states = ('completed', 'failed')

    def __init__(self, task_id, task_status):
        self.id = task_id
        assert 'task' in task_status, 'No task data for {}'.format(self.id)
        assert 'status' in task_status, 'No status data for {}'.format(self.id)
        self.task = task_status['task']
        self.status = task_status['status']

    @property
    def run_id(self):
        return self.status['runs'][-1]['runId']

    @property
    def name(self):
        return self.task['metadata'].get('name', 'unknown')

    @property
    def state(self):
        return self.status['state']

    def load_artifacts(self, queue_service):

        # Process only the supported final states
        # as some tasks do not always have relevant output
        if self.state not in self.valid_states:
            logger.warn('Invalid task state', state=self.state, id=self.id, name=self.name)
            return

        # Load relevant artifacts
        out = {}
        for artifact_name in self.artifacts:
            logger.info('Load artifact', task_id=self.id, artifact=artifact_name)
            try:
                artifact = queue_service.getArtifact(self.id, self.run_id, artifact_name)
                out[artifact_name] = 'response' in artifact and artifact['response'].content or artifact
            except Exception as e:
                logger.warn('Failed to read artifact', task_id=self.id, run_id=self.run_id, artifact=artifact_name, error=e)
                continue

        return out

    def clean_path(self, path):
        '''
        Helper to clean issues path from remote tasks
        '''
        if path.startswith(WORKER_CHECKOUT):
            path = path[len(WORKER_CHECKOUT):]
        if path.startswith('/'):
            path = path[1:]
        return path

    def build_patches(self, artifacts):
        '''
        Some analyzers can provide a patch appliable by developers
        These patches are stored as Taskcluster artifacts and reported to developpers
        Output is a list of tuple (patch name as str, patch content as str)
        '''
        return []
