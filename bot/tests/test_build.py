# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
from unittest import mock

import pytest
from conftest import FIXTURES_DIR, MockQueue

from code_review_bot import IssueType, Level
from code_review_bot.tasks.base import ARTIFACT_DOWNLOAD_TIMEOUT
from code_review_bot.tasks.build import LOG_ARTIFACT, BuildIssue, BuildTask

BUILD_FAILURE_LOG = os.path.join(FIXTURES_DIR, "build_failure_live_backing.log")
LOG_URL = f"http://tc.test/buildTaskId/0/artifacts/{LOG_ARTIFACT}"


def build_task(state, name="build-linux64/opt"):
    return BuildTask(
        "buildTaskId",
        {
            "task": {"metadata": {"name": name}},
            "status": {"taskId": "buildTaskId", "state": state, "runs": [{"runId": 0}]},
        },
    )


@pytest.mark.parametrize("state", ["completed", "exception", "running"])
def test_parse_issues_without_failure(mock_revision, state):
    assert build_task(state).parse_issues({}, mock_revision) == []


def test_parse_issues_failed(mock_revision):
    task = build_task("failed")
    issues = task.parse_issues({}, mock_revision)

    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, BuildIssue)
    assert issue.type_ == IssueType.BuildTest
    assert issue.task_id == "buildTaskId"
    assert issue.analyzer is task
    assert issue.revision is mock_revision
    assert issue.level == Level.Error
    assert issue.message == "build failed: build-linux64/opt "
    assert issue.error_lines == []


def test_parse_issues_without_artifacts(mock_revision):
    issues = build_task("failed").parse_issues(None, mock_revision)

    assert len(issues) == 1
    assert issues[0].error_lines == []


def test_parse_issues_with_log(mock_revision):
    with open(BUILD_FAILURE_LOG, "rb") as f:
        issues = build_task("failed").parse_issues(
            {LOG_ARTIFACT: f.read()}, mock_revision
        )

    assert len(issues) == 1
    assert issues[0].error_lines == [
        "/builds/worker/checkouts/gecko/dom/media/webaudio/AudioSinkInfo.h:18:1: error: final class 'AudioSinkInfo' uses NS_DECL_CYCLE_COLLECTING_ISUPPORTS",
        "/builds/worker/checkouts/gecko/dom/media/webaudio/AudioContext.cpp:899:21: error: arguments must all be strong refs",
        "'mach build -v' did not run successfully. Please check log for errors.",
        "[taskcluster:error] exit status 255",
    ]


def test_parse_issues_with_empty_log(mock_revision):
    issues = build_task("failed").parse_issues({LOG_ARTIFACT: None}, mock_revision)

    assert len(issues) == 1
    assert issues[0].error_lines == []


def test_load_artifacts_failed():
    queue = MockQueue()
    with open(BUILD_FAILURE_LOG) as f:
        content = f.read()
    queue.session.add("get", LOG_URL, content)

    assert build_task("failed").load_artifacts(queue) == {
        LOG_ARTIFACT: content.encode()
    }


def test_load_artifacts_timeout():
    queue = MockQueue()
    queue.session = mock.Mock()
    queue.session.get.return_value.content = b"log"

    assert build_task("failed").load_artifacts(queue) == {LOG_ARTIFACT: b"log"}
    queue.session.get.assert_called_once_with(
        LOG_URL, stream=True, allow_redirects=True, timeout=ARTIFACT_DOWNLOAD_TIMEOUT
    )


def test_load_artifacts_missing_log():
    queue = MockQueue()
    queue.session.reset()

    assert build_task("failed").load_artifacts(queue) == {}


def test_load_artifacts_download_error():
    queue = MockQueue()
    queue.session = mock.Mock()
    queue.session.get.side_effect = Exception("connection reset")

    assert build_task("failed").load_artifacts(queue) == {}


@pytest.mark.parametrize("state", ["completed", "exception", "running"])
def test_load_artifacts_not_failed(state):
    queue = MockQueue()
    queue.session = mock.Mock()

    assert build_task(state).load_artifacts(queue) is None
    queue.session.get.assert_not_called()


def test_build_issue(mock_revision):
    issue = build_task("failed").parse_issues({}, mock_revision)[0]

    assert issue.display_name == "build-linux64/opt"
    assert issue.hash == f"{mock_revision}-build-linux64/opt"
    assert issue.is_publishable() is True
    assert issue.validates() is True
    assert issue.is_build_error() is True
    assert issue.as_text() == "build failed: build-linux64/opt "
    assert issue.as_markdown() == (
        "\n## build failure\n\n- **build**: build-linux64/opt\n\n"
        "```\nbuild failed: build-linux64/opt \n```\n"
    )
    assert issue.as_error() == (
        "* [build-linux64/opt](https://firefox-ci-tc.services.mozilla.com/tasks/buildTaskId) "
        "([log link](https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task/buildTaskId/runs/0/artifacts/public/logs/live_backing.log))"
    )
    assert issue.as_error_details() == ""
    assert issue.as_error_details(collapsible=True) == ""
    assert issue.as_phabricator_issue() == {
        "namespace": "code-review",
        "name": "build-linux64/opt",
        "result": "fail",
        "details": f"Code review bot found a **build error**: \n{issue.as_error()}",
        "format": "remarkup",
    }
    assert issue.as_dict() == {
        "analyzer": "build-linux64/opt",
        "level": "error",
        "message": "build failed: build-linux64/opt ",
        "validates": True,
        "publishable": True,
        "hash": f"{mock_revision}-build-linux64/opt",
        "task_id": "buildTaskId",
        "error_lines": [],
    }


def test_build_issue_with_error_lines(mock_revision):
    task = build_task("failed")
    issue = BuildIssue(
        task_id=task.id,
        analyzer=task,
        revision=mock_revision,
        level=Level.Error,
        message=f"build failed: {task.display_name} ",
        error_lines=["foo.cpp:1:1: error: broken", "gmake: *** Error 1"],
    )

    assert issue.as_error_details() == (
        "\n```\nfoo.cpp:1:1: error: broken\ngmake: *** Error 1\n```\n"
    )
    assert issue.as_error_details(collapsible=True) == (
        "\n<details>\n<summary>2 error lines from the log</summary>\n\n"
        "```\nfoo.cpp:1:1: error: broken\ngmake: *** Error 1\n```\n\n</details>\n"
    )
    assert issue.as_phabricator_issue() == {
        "namespace": "code-review",
        "name": "build-linux64/opt",
        "result": "fail",
        "details": (
            f"Code review bot found a **build error**: \n{issue.as_error()}"
            "\n```\nfoo.cpp:1:1: error: broken\ngmake: *** Error 1\n```\n"
        ),
        "format": "remarkup",
    }
    assert issue.as_dict()["error_lines"] == [
        "foo.cpp:1:1: error: broken",
        "gmake: *** Error 1",
    ]
