# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from unittest import mock

from static_analysis_bot.revisions import Revision


class MockRevision(Revision):
    '''
    Fake revision to easily set properties
    '''
    def __init__(self, namespaces, details):
        self._namespaces = namespaces
        self._details = details

    @property
    def namespaces(self):
        return self._namespaces

    def as_dict(self):
        return self._details


def test_taskcluster_index(mock_config, mock_workflow, mock_try_task):
    '''
    Test the Taskcluster indexing API
    by mocking an online taskcluster state
    '''
    from static_analysis_bot.config import TaskCluster
    mock_config.taskcluster = TaskCluster('/tmp/dummy', '12345deadbeef', 0, False)
    mock_workflow.index_service = mock.Mock()
    rev = MockRevision(
        namespaces=['mock.1234'],
        details={'id': '1234', 'someData': 'mock', 'state': 'done', },
    )
    mock_workflow.index(rev, test='dummy')

    assert mock_workflow.index_service.insertTask.call_count == 3
    calls = mock_workflow.index_service.insertTask.call_args_list

    # First call with namespace
    namespace, args = calls[0][0]
    assert namespace == 'project.releng.services.project.test.static_analysis_bot.mock.1234'
    assert args['taskId'] == '12345deadbeef'
    assert args['data']['test'] == 'dummy'
    assert args['data']['id'] == '1234'
    assert args['data']['source'] == 'try'
    assert args['data']['try_task_id'] == 'remoteTryTask'
    assert args['data']['try_group_id'] == 'remoteTryGroup'
    assert args['data']['someData'] == 'mock'
    assert 'indexed' in args['data']

    # Second call with sub namespace
    namespace, args = calls[1][0]
    assert namespace == 'project.releng.services.project.test.static_analysis_bot.mock.1234.12345deadbeef'
    assert args['taskId'] == '12345deadbeef'
    assert args['data']['test'] == 'dummy'
    assert args['data']['id'] == '1234'
    assert args['data']['source'] == 'try'
    assert args['data']['try_task_id'] == 'remoteTryTask'
    assert args['data']['try_group_id'] == 'remoteTryGroup'
    assert args['data']['someData'] == 'mock'
    assert 'indexed' in args['data']

    # Third call for monitoring
    namespace, args = calls[2][0]
    assert namespace == 'project.releng.services.tasks.12345deadbeef'
    assert args['taskId'] == '12345deadbeef'
    assert args['data']['test'] == 'dummy'
    assert args['data']['id'] == '1234'
    assert args['data']['source'] == 'try'
    assert args['data']['try_task_id'] == 'remoteTryTask'
    assert args['data']['try_group_id'] == 'remoteTryGroup'
    assert args['data']['monitoring_restart'] is False


def test_monitoring_restart(mock_config, mock_workflow):
    '''
    Test the Taskcluster indexing API and restart capabilities
    '''
    from static_analysis_bot.config import TaskCluster
    mock_config.taskcluster = TaskCluster('/tmp/dummy', 'someTaskId', 0, False)
    mock_workflow.index_service = mock.Mock()
    rev = MockRevision([], {})

    # Unsupported error code
    mock_workflow.index(rev, test='dummy', error_code='nope', state='error')
    assert mock_workflow.index_service.insertTask.call_count == 1
    calls = mock_workflow.index_service.insertTask.call_args_list
    namespace, args = calls[0][0]
    assert namespace == 'project.releng.services.tasks.someTaskId'
    assert args['taskId'] == 'someTaskId'
    assert args['data']['monitoring_restart'] is False

    # watchdog should be restated
    mock_workflow.index(rev, test='dummy', error_code='watchdog', state='error')
    assert mock_workflow.index_service.insertTask.call_count == 2
    calls = mock_workflow.index_service.insertTask.call_args_list
    namespace, args = calls[1][0]
    assert namespace == 'project.releng.services.tasks.someTaskId'
    assert args['taskId'] == 'someTaskId'
    assert args['data']['monitoring_restart'] is True

    # Invalid state
    mock_workflow.index(rev, test='dummy', state='running')
    assert mock_workflow.index_service.insertTask.call_count == 3
    calls = mock_workflow.index_service.insertTask.call_args_list
    namespace, args = calls[2][0]
    assert namespace == 'project.releng.services.tasks.someTaskId'
    assert args['taskId'] == 'someTaskId'
    assert args['data']['monitoring_restart'] is False
