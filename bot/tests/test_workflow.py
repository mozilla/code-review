# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from unittest import mock


def test_taskcluster_index(mock_workflow, mock_try_config):
    '''
    Test the Taskcluster indexing API
    by mocking an online taskcluster state
    '''
    from static_analysis_bot.config import TaskCluster
    from static_analysis_bot.revisions import Revision
    mock_try_config.taskcluster = TaskCluster('/tmp/dummy', '12345deadbeef', 0, False)
    mock_workflow.index_service = mock.Mock()
    rev = Revision()
    rev.namespaces = ['mock.1234']
    rev.as_dict = lambda: {'id': '1234', 'someData': 'mock'}
    mock_workflow.index(rev, test='dummy')

    assert mock_workflow.index_service.insertTask.call_count == 2
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
