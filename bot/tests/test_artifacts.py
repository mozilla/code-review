# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from unittest import mock

import pytest
from conftest import MockQueue

from code_review_bot.tasks.base import ARTIFACT_DOWNLOAD_TIMEOUT, AnalysisTask


class TestTask(AnalysisTask):
    def parse_issues(*args, **kwargs):
        return []


def test_loading_artifacts(log):
    """
    Test Taskcluster artifacts loading workflow
    """
    assert log.events == []

    task = TestTask(
        "testTask",
        {
            "task": {"metadata": {"name": "test-task"}},
            "status": {"state": "xxx", "runs": [{"runId": 0}]},
        },
    )

    # Add a dummy artifact to load
    queue = MockQueue()
    queue.configure({"testTask": {"artifacts": {"test.txt": "Hello World"}}})
    task.artifacts = ["test.txt"]

    # Unsupported task state
    assert task.load_artifacts(queue) is None
    assert task.state == "xxx"
    assert log.has("Invalid task state", state="xxx", level="warning")

    # Invalid task state
    log.events = []
    task.status["state"] = "running"
    assert task.load_artifacts(queue) is None
    assert task.state == "running"
    assert log.has("Invalid task state", state="running", level="warning")

    # Valid task state
    log.events = []
    task.status["state"] = "completed"
    assert task.load_artifacts(queue) == {"test.txt": b"Hello World"}
    assert task.state == "completed"
    assert log.has(
        "Load artifact", task_id="testTask", artifact="test.txt", level="info"
    )

    # Skip completed tasks
    task.valid_states = ("failed",)
    task.skipped_states = ("completed",)

    log.events = []
    task.status["state"] = "completed"
    assert task.load_artifacts(queue) is None
    assert task.state == "completed"
    assert log.has("Skipping task", id="testTask", name="test-task", level="info")


def test_loading_artifacts_errors():
    task = TestTask(
        "testTask",
        {
            "task": {"metadata": {"name": "test-task"}},
            "status": {"state": "completed", "runs": [{"runId": 0}]},
        },
    )
    task.artifacts = ["test.txt"]
    queue = MockQueue()

    queue.configure({"testTask": {"artifacts": {}}})
    assert task.load_artifacts(queue) == {}

    queue.session = mock.Mock()
    queue.session.get.side_effect = ConnectionError("connection reset")
    with pytest.raises(ConnectionError, match="connection reset"):
        task.load_artifacts(queue)
    queue.session.get.assert_called_once_with(
        "http://tc.test/testTask/0/artifacts/test.txt",
        stream=True,
        allow_redirects=True,
        timeout=ARTIFACT_DOWNLOAD_TIMEOUT,
    )
