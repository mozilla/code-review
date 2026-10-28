# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
from pathlib import Path
from textwrap import dedent

import responses
from conftest import FIXTURES_DIR
from responses import matchers

from code_review_bot.analysis import AnalysisMode
from code_review_bot.report.builderrors import EMAIL_CONTENT_LIMIT, BuildErrorsReporter
from code_review_bot.sources.github import GITHUB_COMMENT_LIMIT

MAIL_CONTENT_BUILD_ERRORS = """
# [Code Review bot](https://github.com/mozilla/code-review) found 2 build errors on [D51](https://phabricator.test/D51)


**Message**: ```Unidentified symbol```
**Location**: some/file/path:0


**Message**: ```Unidentified symbol```
**Location**: some/file/path:1
"""


def test_builderrors_taskcluster(
    log, mock_config, mock_clang_tidy_issues, mock_revision, mock_taskcluster_config
):
    """
    Test builderrors sending email to the author of the Phabricator revision
    """

    def _check_email(request):
        payload = json.loads(request.body)

        assert payload["subject"] == "Code Review bot found 2 build errors on D51"
        assert payload["address"] == "test@mozilla.com"
        assert payload["content"] == MAIL_CONTENT_BUILD_ERRORS

        return (200, {}, "")  # ack

    # Add mock taskcluster email to check output
    responses.add_callback(
        responses.POST,
        "http://taskcluster.test/api/notify/v1/email",
        callback=_check_email,
    )

    # Publish email
    conf = {"emails": ["test@mozilla.com"]}
    r = BuildErrorsReporter(conf)

    r.publish(mock_clang_tidy_issues, mock_revision, [], [], [], AnalysisMode.Lint)

    assert log.has("Send build error email", to="test@mozilla.com")


def test_builderrors_github(
    log,
    mock_config,
    mock_clang_tidy_issues,
    mock_github_revision,
    mock_taskcluster_config,
):
    """
    Test builderrors commenting on the github Pull Request to mention build errors
    """
    mock_taskcluster_config.secrets = {
        "REPORTERS": [
            {
                "reporter": "github",
                "client_id": "client_id",
                "private_key_pem": (Path(FIXTURES_DIR) / "private_key.pem").read_text(),
                "installation_id": 123456789,
            }
        ]
    }

    responses.add(
        responses.POST,
        "https://api.github.com:443/repos/owner/repo-name/pulls/1/comments",
        match=[
            matchers.json_params_matcher(
                {
                    "body": dedent("""
                Hello @test_user,
                [Code Review bot](https://github.com/mozilla/code-review) detected 1 build errors when analyzing this Pull Request:

                **Message**: ```Some Error Message```
                **Location**: dom/animation/Animation.cpp:57
            """).lstrip()
                }
            )
        ],
    )
    r = BuildErrorsReporter({})
    r.publish(
        mock_clang_tidy_issues, mock_github_revision, [], [], [], AnalysisMode.Lint
    )


def _build_issues(mock_task, revision):
    from code_review_bot import Level
    from code_review_bot.tasks.build import BuildIssue, BuildTask

    return [
        BuildIssue(
            task_id="build-linux64/opt-ID",
            analyzer=mock_task(BuildTask, "build-linux64/opt"),
            revision=revision,
            level=Level.Error,
            message="build failed: build-linux64/opt ",
            error_lines=["foo.cpp:1:1: error: broken"],
        ),
        BuildIssue(
            task_id="build-win64/opt-ID",
            analyzer=mock_task(BuildTask, "build-win64/opt"),
            revision=revision,
            level=Level.Error,
            message="build failed: build-win64/opt ",
        ),
    ]


LINUX_BUILD_ERROR = "* [build-linux64/opt](https://firefox-ci-tc.services.mozilla.com/tasks/build-linux64/opt-ID) ([log link](https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task/build-linux64/opt-ID/runs/0/artifacts/public/logs/live_backing.log))"
WIN_BUILD_ERROR = "* [build-win64/opt](https://firefox-ci-tc.services.mozilla.com/tasks/build-win64/opt-ID) ([log link](https://firefox-ci-tc.services.mozilla.com/api/queue/v1/task/build-win64/opt-ID/runs/0/artifacts/public/logs/live_backing.log))"


def test_builderrors_taskcluster_build_issues(
    log, mock_config, mock_revision, mock_taskcluster_config, mock_task
):
    def _check_email(request):
        payload = json.loads(request.body)

        assert payload["subject"] == "Code Review bot found 2 build errors on D51"
        assert payload["content"] == (
            "\n# [Code Review bot](https://github.com/mozilla/code-review) found 2 build errors on [D51](https://phabricator.test/D51)\n\n"
            f"{LINUX_BUILD_ERROR}\n```\nfoo.cpp:1:1: error: broken\n```\n\n"
            f"{WIN_BUILD_ERROR}"
        )

        return (200, {}, "")

    responses.add_callback(
        responses.POST,
        "http://taskcluster.test/api/notify/v1/email",
        callback=_check_email,
    )

    r = BuildErrorsReporter({"emails": ["test@mozilla.com"]})
    r.publish(
        _build_issues(mock_task, mock_revision),
        mock_revision,
        [],
        [],
        [],
        AnalysisMode.BuildTest,
    )

    assert log.has("Send build error email", to="test@mozilla.com")


def test_builderrors_github_build_issues(
    mock_config,
    mock_github_revision,
    mock_taskcluster_config,
    mock_task,
):
    responses.add(
        responses.POST,
        "https://api.github.com:443/repos/owner/repo-name/pulls/1/comments",
        match=[
            matchers.json_params_matcher(
                {
                    "body": "\n".join(
                        [
                            "Hello @test_user,",
                            "[Code Review bot](https://github.com/mozilla/code-review) detected 2 build errors when analyzing this Pull Request:",
                            LINUX_BUILD_ERROR,
                            "\n<details>\n<summary>1 error line from the log</summary>\n\n"
                            "```\nfoo.cpp:1:1: error: broken\n```\n\n</details>\n",
                            WIN_BUILD_ERROR,
                        ]
                    )
                }
            )
        ],
    )
    r = BuildErrorsReporter(
        {
            "client_id": "client_id",
            "private_key_pem": (Path(FIXTURES_DIR) / "private_key.pem").read_text(),
            "installation_id": 123456789,
        }
    )
    r.publish(
        _build_issues(mock_task, mock_github_revision),
        mock_github_revision,
        [],
        [],
        [],
        AnalysisMode.BuildTest,
    )


def _large_build_issues(mock_task, revision):
    from code_review_bot import Level
    from code_review_bot.tasks.build import BuildIssue, BuildTask

    return [
        BuildIssue(
            task_id=f"build-{i}/opt-ID",
            analyzer=mock_task(BuildTask, f"build-{i}/opt"),
            revision=revision,
            level=Level.Error,
            message=f"build failed: build-{i}/opt ",
            error_lines=[f"foo.cpp:{j}:1: error: {'x' * 450}" for j in range(20)],
        )
        for i in range(15)
    ]


def test_builderrors_taskcluster_build_issues_too_large(
    log, mock_config, mock_revision, mock_taskcluster_config, mock_task
):
    issues = _large_build_issues(mock_task, mock_revision)

    def _check_email(request):
        content = json.loads(request.body)["content"]

        assert len(content) <= EMAIL_CONTENT_LIMIT
        for issue in issues:
            assert issue.as_error() in content
        assert content.count("```") == 20
        assert content.endswith(
            "Error details for 5 failed tasks were omitted to keep this message "
            "under its size limit; see the linked logs."
        )

        return (200, {}, "")

    responses.add_callback(
        responses.POST,
        "http://taskcluster.test/api/notify/v1/email",
        callback=_check_email,
    )

    r = BuildErrorsReporter({"emails": ["test@mozilla.com"]})
    r.publish(issues, mock_revision, [], [], [], AnalysisMode.BuildTest)

    assert log.has("Send build error email", to="test@mozilla.com")


def test_builderrors_github_build_issues_too_large(
    mock_config,
    mock_github_revision,
    mock_taskcluster_config,
    mock_task,
):
    responses.add(
        responses.POST,
        "https://api.github.com:443/repos/owner/repo-name/pulls/1/comments",
        json={},
    )
    issues = _large_build_issues(mock_task, mock_github_revision)
    r = BuildErrorsReporter(
        {
            "client_id": "client_id",
            "private_key_pem": (Path(FIXTURES_DIR) / "private_key.pem").read_text(),
            "installation_id": 123456789,
        }
    )
    r.publish(issues, mock_github_revision, [], [], [], AnalysisMode.BuildTest)

    body = json.loads(responses.calls[-1].request.body)["body"]
    assert len(body) <= GITHUB_COMMENT_LIMIT
    for issue in issues:
        assert issue.as_error() in body
    assert body.count("<details>") == body.count("</details>") == 6
    assert body.endswith(
        "Error details for 9 failed tasks were omitted to keep this message "
        "under its size limit; see the linked logs."
    )
