# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest

from code_review_bot import IssueType, Level
from code_review_bot.tasks.build import BuildIssue, BuildTask


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
    }
