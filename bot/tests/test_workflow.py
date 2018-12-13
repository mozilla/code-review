# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from unittest import mock


def test_taskcluster_index(mock_workflow, mock_config, mock_revision):
    '''
    Test the Taskcluster indexing API
    by mocking an online taskcluster state
    '''
    from static_analysis_bot.config import TaskCluster
    mock_config.taskcluster = TaskCluster('/tmp/dummy', '12345deadbeef', 0, False)
    mock_workflow.index_service = mock.Mock()
    mock_revision.namespaces = ['mock.1234']
    mock_revision.as_dict = lambda: {'id': '1234', 'source': 'mock'}
    mock_workflow.index(mock_revision, test='dummy')

    args = mock_workflow.index_service.insertTask.call_args[0]
    assert args[0] == 'project.releng.services.project.test.static_analysis_bot.mock.1234'
    assert args[1]['taskId'] == '12345deadbeef'
    assert args[1]['data']['test'] == 'dummy'
    assert args[1]['data']['id'] == '1234'
    assert args[1]['data']['source'] == 'mock'
    assert 'indexed' in args[1]['data']
