# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
from pathlib import Path
from textwrap import dedent

import responses
from conftest import FIXTURES_DIR
from responses import matchers

from code_review_bot.report.builderrors import BuildErrorsReporter

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

    r.publish(mock_clang_tidy_issues, mock_revision, [], [], [])

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
    r.publish(mock_clang_tidy_issues, mock_github_revision, [], [], [])
