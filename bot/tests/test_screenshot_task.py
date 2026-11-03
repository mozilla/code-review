import pytest

from code_review_bot.tasks.screenshot import ScreenshotTestTask


def _task(state):
    return ScreenshotTestTask(
        "12345deadbeef",
        {
            "task": {"metadata": {"name": "screenshot-test-fenix-screenshot-test"}},
            "status": {
                "taskId": "12345deadbeef",
                "state": state,
                "runs": [{"runId": 0}],
            },
        },
    )


@pytest.fixture
def queue(mock_taskcluster_config):
    queue = mock_taskcluster_config.get_service("queue")
    queue.options = {"rootUrl": "http://taskcluster.test"}
    return queue


def test_failed_with_report(queue, mock_revision):
    queue.configure(
        {"12345deadbeef": {"artifacts": {"public/screenshot-diffs/index.html": "<html/>"}}}
    )
    task = _task("failed")
    artifacts = task.load_artifacts(queue)
    assert "public/screenshot-diffs/index.html" in artifacts
    notice = task.build_notice(artifacts, mock_revision)
    assert (
        "[test report](https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task/"
        "12345deadbeef/runs/0/artifacts/public/screenshot-diffs/index.html)"
    ) in notice


def test_failed_without_report(mock_revision):
    assert _task("failed").build_notice({}, mock_revision) == ""


def test_completed_skipped(queue):
    assert _task("completed").load_artifacts(queue) is None
