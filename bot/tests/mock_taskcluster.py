# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import namedtuple

MockArtifactResponse = namedtuple('MockArtifactResponse', 'content')


class MockQueue(object):
    '''
    Mock the Taskcluster queue, by using fake tasks descriptions, relations and artifacts
    '''

    def configure(self, relations):
        # Create tasks
        assert isinstance(relations, dict)
        self._tasks = {
            task_id: {
                'dependencies': desc.get('dependencies', []),
                'metadata': {
                    'name': desc.get('name', 'source-test-mozlint-{}'.format(task_id)),
                },
                'payload': {
                    'image': desc.get('image', 'alpine'),
                    'env': desc.get('env', {}),
                }
            }
            for task_id, desc in relations.items()
        }

        # Create status
        self._status = {
            task_id: {
                'status': {
                    'taskId': task_id,
                    'state': desc.get('state', 'completed'),
                    'runs': [
                        {
                            'runId': 0,
                        }
                    ]
                }
            }
            for task_id, desc in relations.items()
        }

        # Create artifacts
        self._artifacts = {
            task_id: {
                'artifacts': [
                    {
                        'name': name,
                        'storageType': 'dummyStorage',
                        'contentType': isinstance(artifact, (dict, list)) and 'application/json' or 'text/plain',
                        'content': artifact,
                    }
                    for name, artifact in desc.get('artifacts', {}).items()
                ]
            }
            for task_id, desc in relations.items()
        }

    def task(self, task_id):
        return self._tasks[task_id]

    def status(self, task_id):
        return self._status[task_id]

    def listTaskGroup(self, group_id):
        return {
            'tasks': [
                {
                    'task': self.task(task_id),
                    'status': self.status(task_id)['status'],
                }
                for task_id in self._tasks.keys()
            ]
        }

    def listArtifacts(self, task_id, run_id):
        return self._artifacts.get(task_id, {})

    def getArtifact(self, task_id, run_id, artifact_name):
        artifacts = self._artifacts.get(task_id, {})
        if not artifacts:
            return

        artifact = next(filter(lambda a: a['name'] == artifact_name, artifacts['artifacts']))
        if artifact['contentType'] == 'application/json':
            return artifact['content']
        return {
            'response': MockArtifactResponse(artifact['content'].encode('utf-8')),
        }


class MockIndex(object):
    def configure(self, tasks):
        self.tasks = tasks

    def findTask(self, route):
        task_id = next(iter([task_id for task_id, task in self.tasks.items() if task.get('route') == route]), None)
        if task_id is None:
            raise Exception('Task {} not found'.format(route))
        return {
            'taskId': task_id
        }
