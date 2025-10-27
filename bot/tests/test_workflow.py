# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
from datetime import datetime
from unittest import mock

import pytest
import responses

from code_review_bot.config import Settings
from code_review_bot.tasks.clang_format import ClangFormatIssue, ClangFormatTask
from code_review_bot.tasks.clang_tidy import ClangTidyTask
from code_review_bot.tasks.clang_tidy_external import ExternalTidyTask
from code_review_bot.tasks.lint import MozLintTask
from code_review_bot.tasks.tgdiff import TaskGraphDiffTask


@pytest.mark.parametrize(
    "task_name, result, on_autoland",
    [
        ("source-test-clang-tidy", ClangTidyTask, False),
        ("source-test-clang-tidy", ClangTidyTask, True),
        ("source-test-clang-external", ExternalTidyTask, False),
        ("source-test-clang-external", ExternalTidyTask, True),
        ("source-test-mozlint-eslint", MozLintTask, False),
        ("source-test-mozlint-eslint", MozLintTask, True),
        ("source-test-mozlint-whatever", MozLintTask, False),
        ("source-test-mozlint-whatever", MozLintTask, True),
        ("source-test-clang-format", ClangFormatTask, False),
        ("source-test-clang-format", ClangFormatTask, True),
        ("source-test-taskgraph-diff", TaskGraphDiffTask, False),
        ("source-test-taskgraph-diff", TaskGraphDiffTask, True),
        ("source-test-unsupported", None, False),
        ("source-test-unsupported", None, True),
    ],
)
def test_build_task(task_name, result, on_autoland, mock_config, mock_workflow):
    """
    Test the build_task method with different task payloads
    """
    # Setup autoland id
    mock_config.autoland_task_id = "someTaskId" if on_autoland else None
    mock_config.autoland_group_id = "someGroupId" if on_autoland else None

    task_status = {
        "task": {"metadata": {"name": task_name}},
        "status": {"taskId": "someTaskId"},
    }

    # Check exceptions thrown
    if result is Exception:
        with pytest.raises(Exception) as e:
            mock_workflow.build_task(task_status)
        assert str(e.value) == f"Unsupported task {task_name}"
        return

    # Normal cases
    task = mock_workflow.build_task(task_status)
    if result is None:
        assert task is None
    else:
        assert isinstance(task, result)


def test_on_production(mock_config, mock_repositories):
    """
    Test the production environment detection
    """
    # By default mock_config is not as production
    assert mock_config.app_channel == "test"
    assert mock_config.taskcluster.local is True
    assert mock_config.on_production is False
    assert mock_config.taskcluster_url is None

    # Taskcluster env + testing is not production
    os.environ["TASK_ID"] = "testingTask"
    os.environ["RUN_ID"] = "0"
    testing = Settings()
    testing.setup("testing", [], mock_repositories)
    assert testing.app_channel == "testing"
    assert testing.taskcluster.local is False
    assert testing.on_production is False
    assert (
        testing.taskcluster_url
        == "https://firefox-ci-tc.services.mozilla.com/tasks/testingTask"
    )

    # Taskcluster env + production is production
    os.environ["TASK_ID"] = "prodTask"
    os.environ["RUN_ID"] = "0"
    testing = Settings()
    testing.setup("production", [], mock_repositories)
    assert testing.app_channel == "production"
    assert testing.taskcluster.local is False
    assert testing.on_production is True
    assert (
        testing.taskcluster_url
        == "https://firefox-ci-tc.services.mozilla.com/tasks/prodTask"
    )


def test_before_after(mock_taskcluster_config, mock_workflow, mock_task, mock_revision):
    """
    Test the before/after feature running a try task workflow.
    Issues that are unknown to the backend are tagged as new issues.
    """
    mock_taskcluster_config.secrets = {"BEFORE_AFTER_RATIO": 1}
    issues = [
        ClangFormatIssue(
            mock_task(ClangFormatTask, "source-test-clang-format"),
            "outside/of/the/patch.cpp",
            [(42, 42, b"This is a new warning.")],
            mock_revision,
        ),
        ClangFormatIssue(
            mock_task(ClangFormatTask, "source-test-clang-format"),
            "outside/of/the/patch.cpp",
            [(42, 42, b"This is a warning known by the backend.")],
            mock_revision,
        ),
    ]
    mock_workflow.publish = mock.Mock()
    mock_workflow.find_issues = mock.Mock()
    mock_workflow.find_issues.return_value = (
        issues,
        # No failure nor notices nor reviewers
        [],
        [],
        [],
    )
    mock_workflow.queue_service.task = lambda x: {}
    mock_workflow.mercurial_repository = None
    mock_workflow.backend_api.url = "https://backend.test"
    mock_workflow.backend_api.username = "root"
    mock_workflow.backend_api.password = "hunter2"
    for index, hash_val in enumerate(("aaaa", "bbbb")):
        issues[index].hash = hash_val

    current_date = datetime.now().strftime("%Y-%m-%d")
    responses.add(
        responses.GET,
        f"https://backend.test/v1/issues/mozilla-central/?path=outside%2Fof%2Fthe%2Fpatch.cpp&date={current_date}",
        json={
            "count": 2,
            "previous": None,
            "next": None,
            "results": [
                {"id": "issue 1", "hash": "bbbb"},
                {"id": "issue 42", "hash": "xxxx"},
            ],
        },
    )

    # Set backend ID as the publication is disabled for tests
    mock_revision.id = 1337
    assert mock_revision.before_after_feature is True
    mock_workflow.run(mock_revision)
    assert mock_workflow.publish.call_args_list == [
        mock.call(
            mock_revision,
            issues,
            [],
            [],
            [],
        )
    ]
    assert issues[0].new_issue is True
    assert issues[1].new_issue is False
