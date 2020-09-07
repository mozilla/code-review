# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json

import pytest
import responses

from code_review_bot.tasks.clang_format import ClangFormatTask
from code_review_bot.tasks.clang_tidy import ClangTidyTask

MAIL_CONTENT = """
# Found 3 publishable issues (5 total)

* **MockIssue**: 3 publishable (5 total)

Review Url: https://phabricator.test/D51

## Improvement patches:

* Improvement patch from clang-tidy: {results}/clang-tidy-PHID-DIFF-test.diff
* Improvement patch from clang-format: {results}/clang-format-PHID-DIFF-test.diff

This is the mock issue n°0

This is the mock issue n°1

This is the mock issue n°2

This is the mock issue n°3

This is the mock issue n°4"""

MAIL_CONTENT_BUILD_ERRORS = """
# [Code Review bot](https://github.com/mozilla/code-review) found 2 build errors on [D51](https://phabricator.test/D51)


**Message**: ```Unidentified symbol```
**Location**: some/file/path:0


**Message**: ```Unidentified symbol```
**Location**: some/file/path:1
"""


def test_conf(mock_config, mock_taskcluster_config):
    """
    Test mail reporter configuration
    """
    from code_review_bot.report.mail import MailReporter

    # Missing emails conf
    with pytest.raises(AssertionError):
        MailReporter({})

    # Missing emails
    conf = {"emails": []}
    with pytest.raises(AssertionError):
        MailReporter(conf)

    # Valid emails
    conf = {"emails": ["test@mozilla.com"]}
    r = MailReporter(conf)
    assert r.emails == ["test@mozilla.com"]

    conf = {"emails": ["test@mozilla.com", "test2@mozilla.com", "test3@mozilla.com"]}
    r = MailReporter(conf)
    assert r.emails == ["test@mozilla.com", "test2@mozilla.com", "test3@mozilla.com"]


def test_mail(
    mock_config, mock_issues, mock_revision, mock_taskcluster_config, mock_task
):
    """
    Test mail sending through Taskcluster
    """
    from code_review_bot.report.mail import MailReporter
    from code_review_bot.revisions import ImprovementPatch

    def _check_email(request):
        payload = json.loads(request.body)

        assert payload["subject"] in (
            "[test] New Static Analysis Phabricator #42 - PHID-DIFF-test",
        )
        assert payload["address"] == "test@mozilla.com"
        assert payload["template"] == "fullscreen"
        assert payload["content"] == MAIL_CONTENT.format(
            results=mock_config.taskcluster.results_dir
        )

        return (200, {}, "")  # ack

    # Add mock taskcluster email to check output
    responses.add_callback(
        responses.POST,
        "http://taskcluster.test/api/notify/v1/email",
        callback=_check_email,
    )

    # Publish email
    conf = {"emails": ["test@mozilla.com"]}
    r = MailReporter(conf)

    mock_revision.improvement_patches = [
        ImprovementPatch(
            mock_task(ClangTidyTask, "clang-tidy"),
            repr(mock_revision),
            "Some code fixes",
        ),
        ImprovementPatch(
            mock_task(ClangFormatTask, "clang-format"),
            repr(mock_revision),
            "Some lint fixes",
        ),
    ]
    list(
        map(lambda p: p.write(), mock_revision.improvement_patches)
    )  # trigger local write
    r.publish(mock_issues, mock_revision, [], [])

    # Check stats
    assert r.calc_stats(mock_issues) == [
        {
            "analyzer": "mock-analyzer",
            "help": None,
            "total": 5,
            "publishable": 3,
            "publishable_paths": ["/path/to/file"],
            "nb_build_errors": 2,
            "nb_defects": 1,
        }
    ]


def test_mail_builderrors(
    log, mock_config, mock_clang_tidy_issues, mock_revision, mock_taskcluster_config
):
    """
    Test mail_builderrors sending through Taskcluster
    """
    from code_review_bot.report.mail_builderrors import BuildErrorsReporter

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

    r.publish(mock_clang_tidy_issues, mock_revision, [], [])

    assert log.has("Send build error email", to="test@mozilla.com")
