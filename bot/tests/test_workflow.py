# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from unittest import mock


def test_taskcluster_index(mock_workflow, mock_revision):
    '''
    Test the Taskcluster indexing API
    '''
    mock_workflow.index_service = mock.Mock()
    mock_workflow.on_taskcluster = True
    mock_workflow.taskcluster_task_id = '12345deadbeef'
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
