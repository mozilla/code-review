# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
from unittest import mock

import pytest

from code_review_bot.config import Settings
from code_review_bot.revisions import Revision
from code_review_bot.tasks.clang_format import ClangFormatTask
from code_review_bot.tasks.clang_tidy import ClangTidyTask
from code_review_bot.tasks.coverity import CoverityTask
from code_review_bot.tasks.infer import InferTask
from code_review_bot.tasks.lint import MozLintTask


class MockRevision(Revision):
    """
    Fake revision to easily set properties
    """

    def __init__(self, namespaces, details, repository):
        self._namespaces = namespaces
        self._details = details
        self.repository = repository

    @property
    def namespaces(self):
        return self._namespaces

    def as_dict(self):
        return self._details


def test_taskcluster_index(mock_config, mock_workflow, mock_try_task):
    """
    Test the Taskcluster indexing API
    by mocking an online taskcluster state
    """
    from code_review_bot.config import TaskCluster

    mock_config.taskcluster = TaskCluster("/tmp/dummy", "12345deadbeef", 0, False)
    mock_workflow.index_service = mock.Mock()
    rev = MockRevision(
        namespaces=["mock.1234"],
        details={"id": "1234", "someData": "mock", "state": "done"},
        repository="test-repo",
    )
    mock_workflow.index(rev, test="dummy")

    assert mock_workflow.index_service.insertTask.call_count == 3
    calls = mock_workflow.index_service.insertTask.call_args_list

    # First call with namespace
    namespace, args = calls[0][0]
    assert namespace == "project.relman.test.code-review.mock.1234"
    assert args["taskId"] == "12345deadbeef"
    assert args["data"]["test"] == "dummy"
    assert args["data"]["id"] == "1234"
    assert args["data"]["source"] == "try"
    assert args["data"]["try_task_id"] == "remoteTryTask"
    assert args["data"]["try_group_id"] == "remoteTryGroup"
    assert args["data"]["repository"] == "test-repo"
    assert args["data"]["someData"] == "mock"
    assert "indexed" in args["data"]

    # Second call with sub namespace
    namespace, args = calls[1][0]
    assert namespace == "project.relman.test.code-review.mock.1234.12345deadbeef"
    assert args["taskId"] == "12345deadbeef"
    assert args["data"]["test"] == "dummy"
    assert args["data"]["id"] == "1234"
    assert args["data"]["source"] == "try"
    assert args["data"]["try_task_id"] == "remoteTryTask"
    assert args["data"]["try_group_id"] == "remoteTryGroup"
    assert args["data"]["repository"] == "test-repo"
    assert args["data"]["someData"] == "mock"
    assert "indexed" in args["data"]

    # Third call for monitoring
    namespace, args = calls[2][0]
    assert namespace == "project.relman.tasks.12345deadbeef"
    assert args["taskId"] == "12345deadbeef"
    assert args["data"]["test"] == "dummy"
    assert args["data"]["id"] == "1234"
    assert args["data"]["source"] == "try"
    assert args["data"]["try_task_id"] == "remoteTryTask"
    assert args["data"]["try_group_id"] == "remoteTryGroup"
    assert args["data"]["repository"] == "test-repo"
    assert args["data"]["monitoring_restart"] is False


def test_monitoring_restart(mock_config, mock_workflow):
    """
    Test the Taskcluster indexing API and restart capabilities
    """
    from code_review_bot.config import TaskCluster

    mock_config.taskcluster = TaskCluster("/tmp/dummy", "someTaskId", 0, False)
    mock_workflow.index_service = mock.Mock()
    rev = MockRevision([], {}, "test")

    # Unsupported error code
    mock_workflow.index(rev, test="dummy", error_code="nope", state="error")
    assert mock_workflow.index_service.insertTask.call_count == 1
    calls = mock_workflow.index_service.insertTask.call_args_list
    namespace, args = calls[0][0]
    assert namespace == "project.relman.tasks.someTaskId"
    assert args["taskId"] == "someTaskId"
    assert args["data"]["monitoring_restart"] is False

    # watchdog should be restated
    mock_workflow.index(rev, test="dummy", error_code="watchdog", state="error")
    assert mock_workflow.index_service.insertTask.call_count == 2
    calls = mock_workflow.index_service.insertTask.call_args_list
    namespace, args = calls[1][0]
    assert namespace == "project.relman.tasks.someTaskId"
    assert args["taskId"] == "someTaskId"
    assert args["data"]["monitoring_restart"] is True

    # Invalid state
    mock_workflow.index(rev, test="dummy", state="running")
    assert mock_workflow.index_service.insertTask.call_count == 3
    calls = mock_workflow.index_service.insertTask.call_args_list
    namespace, args = calls[2][0]
    assert namespace == "project.relman.tasks.someTaskId"
    assert args["taskId"] == "someTaskId"
    assert args["data"]["monitoring_restart"] is False


@pytest.mark.parametrize(
    "task_name, result",
    [
        ("source-test-clang-tidy", ClangTidyTask),
        ("source-test-mozlint-eslint", MozLintTask),
        ("source-test-mozlint-whatever", MozLintTask),
        ("source-test-clang-format", ClangFormatTask),
        ("source-test-coverity-coverity", CoverityTask),
        ("source-test-infer-infer", InferTask),
        ("source-test-unsupported", None),
        ("totally-unsupported", Exception),
    ],
)
def test_build_task(task_name, result, mock_workflow):
    """
    Test the build_task method with different task payloads
    """
    task_status = {"task": {"metadata": {"name": task_name}}, "status": {}}

    # Check exceptions thrown
    if result is Exception:
        with pytest.raises(Exception) as e:
            mock_workflow.build_task("someTaskId", task_status)
        assert str(e.value) == f"Unsupported task {task_name}"
        return

    # Normal cases
    task = mock_workflow.build_task("someTaskId", task_status)
    if result is None:
        assert task is None
    else:
        assert isinstance(task, result)


def test_on_production(mock_config):
    """
    Test the production environment detection
    """
    # By default mock_config is not as production
    assert mock_config.app_channel == "test"
    assert mock_config.taskcluster.local is True
    assert mock_config.on_production is False

    # Taskcluster env + testing is not production
    os.environ["TASK_ID"] = "testingTask"
    os.environ["RUN_ID"] = "0"
    testing = Settings()
    testing.setup("testing", "IN_PATCH", [])
    assert testing.app_channel == "testing"
    assert testing.taskcluster.local is False
    assert testing.on_production is False

    # Taskcluster env + production is production
    os.environ["TASK_ID"] = "prodTask"
    os.environ["RUN_ID"] = "0"
    testing = Settings()
    testing.setup("production", "IN_PATCH", [])
    assert testing.app_channel == "production"
    assert testing.taskcluster.local is False
    assert testing.on_production is True
