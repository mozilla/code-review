import pytest

from code_review_bot.tasks.tgdiff import TaskGraphDiffTask


@pytest.fixture
def mock_taskgraph_diff_task():
    tg_task_status = {
        "task": {
            "metadata": {"name": "source-test-taskgraph-diff"},
            "tags": {"trust-domain": "gecko"},
        },
        "status": {
            "taskId": "12345deadbeef",
            "state": "completed",
            "runs": [{"runId": 0}],
        },
    }
    return TaskGraphDiffTask("12345deadbeef", tg_task_status)


@pytest.fixture
def mock_taskgraph_diff_comm_task(mock_taskgraph_diff_task):
    mock_taskgraph_diff_task.artifacts.clear()
    mock_taskgraph_diff_task.extra_reviewers_groups.clear()
    mock_taskgraph_diff_task.task["tags"]["trust-domain"] = "comm"
    return mock_taskgraph_diff_task


def test_load_artifacts_no_summary(mock_taskcluster_config, mock_taskgraph_diff_task):
    queue = mock_taskcluster_config.get_service("queue")
    queue.options = {"rootUrl": "http://taskcluster.test"}
    queue.configure(
        {
            "12345deadbeef": {
                "artifacts": {
                    "public/taskgraph/diffs/diff_mc-onpush.txt": "Some diff",
                    "public/taskgraph/not_a_diff.txt": "Not a diff",
                }
            }
        }
    )

    mock_taskgraph_diff_task.load_artifacts(queue)

    assert mock_taskgraph_diff_task.artifact_urls == {
        "public/taskgraph/diffs/diff_mc-onpush.txt": "http://tc.test/12345deadbeef/0/artifacts/public/taskgraph/diffs/diff_mc-onpush.txt"
    }
    assert mock_taskgraph_diff_task.extra_reviewers_groups == []


def test_load_artifacts_ok_summary(mock_taskcluster_config, mock_taskgraph_diff_task):
    queue = mock_taskcluster_config.get_service("queue")
    queue.options = {"rootUrl": "http://taskcluster.test"}
    queue.configure(
        {
            "12345deadbeef": {
                "artifacts": {
                    "public/taskgraph/diffs/diff_mc-onpush.txt": "Some diff",
                    "public/taskgraph/diffs/summary.json": {
                        "files": {},
                        "status": "OK",
                        "threshold": 20,
                    },
                    "public/taskgraph/not_a_diff.txt": "Not a diff",
                }
            }
        }
    )

    mock_taskgraph_diff_task.load_artifacts(queue)

    # The summary.json is OK, so no extra reviewer group is added and we don't load it in the artifact_urls list
    assert mock_taskgraph_diff_task.artifact_urls == {
        "public/taskgraph/diffs/diff_mc-onpush.txt": "http://tc.test/12345deadbeef/0/artifacts/public/taskgraph/diffs/diff_mc-onpush.txt"
    }
    assert mock_taskgraph_diff_task.extra_reviewers_groups == []


def test_load_artifacts_warning_summary(
    mock_taskcluster_config, mock_taskgraph_diff_task
):
    queue = mock_taskcluster_config.get_service("queue")
    queue.options = {"rootUrl": "http://taskcluster.test"}
    queue.configure(
        {
            "12345deadbeef": {
                "artifacts": {
                    "public/taskgraph/diffs/diff_mc-onpush.txt": "Some diff",
                    "public/taskgraph/diffs/summary.json": {
                        "files": {},
                        "status": "WARNING",
                        "threshold": 20,
                    },
                    "public/taskgraph/not_a_diff.txt": "Not a diff",
                }
            }
        }
    )

    mock_taskgraph_diff_task.load_artifacts(queue)

    # The summary.json is WARNING, so an extra reviewer group is added and we don't load it in the artifact_urls list
    assert mock_taskgraph_diff_task.artifact_urls == {
        "public/taskgraph/diffs/diff_mc-onpush.txt": "http://tc.test/12345deadbeef/0/artifacts/public/taskgraph/diffs/diff_mc-onpush.txt"
    }
    assert mock_taskgraph_diff_task.extra_reviewers_groups == ["taskgraph-reviewers"]


def test_load_artifacts_warning_summary_comm(
    mock_taskcluster_config, mock_taskgraph_diff_comm_task
):
    queue = mock_taskcluster_config.get_service("queue")
    queue.options = {"rootUrl": "http://taskcluster.test"}
    queue.configure(
        {
            "12345deadbeef": {
                "artifacts": {
                    "public/taskgraph/diffs/diff_mc-onpush.txt": "Some diff",
                    "public/taskgraph/diffs/summary.json": {
                        "files": {},
                        "status": "WARNING",
                        "threshold": 20,
                    },
                    "public/taskgraph/not_a_diff.txt": "Not a diff",
                }
            }
        }
    )

    mock_taskgraph_diff_comm_task.load_artifacts(queue)

    # The summary.json is WARNING, but the task is not from gecko so no extra reviewer group is added
    assert mock_taskgraph_diff_comm_task.artifact_urls == {
        "public/taskgraph/diffs/diff_mc-onpush.txt": "http://tc.test/12345deadbeef/0/artifacts/public/taskgraph/diffs/diff_mc-onpush.txt"
    }
    assert mock_taskgraph_diff_comm_task.extra_reviewers_groups == []
