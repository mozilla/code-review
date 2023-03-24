# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os

from code_review_bot.tasks.lint import MozLintIssue
from code_review_bot.tasks.lint import MozLintTask
from conftest import FIXTURES_DIR


def test_flake8_checks(mock_config, mock_revision_setup, mock_hgmo, mock_task):
    """
    Check flake8 check detection
    """

    # Valid issue
    issue = MozLintIssue(
        mock_task(MozLintTask, "mock-lint-flake8"),
        "test.py",
        1,
        "error",
        1,
        "flake8",
        "Dummy test",
        "dummy rule",
        mock_revision_setup,
    )
    assert not issue.is_disabled_check()
    assert issue.validates()

    # Flake8 bad quotes
    issue = MozLintIssue(
        mock_task(MozLintTask, "mock-lint-flake8"),
        "test.py",
        1,
        "error",
        1,
        "flake8",
        "Remove bad quotes or whatever.",
        "Q000",
        mock_revision_setup,
    )
    assert issue.is_disabled_check()
    assert not issue.validates()

    assert issue.as_dict() == {
        "analyzer": "mock-lint-flake8",
        "check": "Q000",
        "column": 1,
        "in_patch": False,
        "level": "error",
        "line": 1,
        "message": "Remove bad quotes or whatever.",
        "nb_lines": 1,
        "path": "test.py",
        "publishable": False,
        "validates": False,
        "hash": "cde6dd7bc43f51fff7361f8db71b5876",
        "fix": None,
    }


def test_as_text(mock_config, mock_revision, mock_hgmo, mock_task):
    """
    Test text export for ClangTidyIssue
    """

    issue = MozLintIssue(
        mock_task(MozLintTask, "mock-lint-flake8"),
        "test.py",
        1,
        "error",
        1,
        "flake8",
        "dummy test withUppercaseChars",
        "dummy rule",
        mock_revision,
    )

    assert (
        issue.as_text() == "Error: Dummy test withUppercaseChars [flake8: dummy rule]"
    )

    assert issue.as_phabricator_lint() == {
        "char": 1,
        "code": "dummy rule",
        "line": 1,
        "name": "mock-lint-flake8",
        "description": "(IMPORTANT) ERROR: dummy test withUppercaseChars",
        "path": "test.py",
        "severity": "error",
    }

    assert issue.as_dict() == {
        "analyzer": "mock-lint-flake8",
        "check": "dummy rule",
        "column": 1,
        "in_patch": False,
        "level": "error",
        "line": 1,
        "message": "dummy test withUppercaseChars",
        "nb_lines": 1,
        "path": "test.py",
        "publishable": True,
        "validates": True,
        "hash": "bd2978ec40c8295d51046e6b8b05ddf7",
        "fix": None,
    }


def test_licence_payload(mock_revision, mock_hgmo):
    """
    Test mozlint licence payload, without a check
    The analyzer name replaces the empty check
    See https://github.com/mozilla/code-review/issues/172
    """
    mock_revision.head_repository = "test-try"
    mock_revision.head_changeset = "deadbeef1234"
    task_status = {
        "task": {"metadata": {"name": "source-test-mozlint-license"}},
        "status": {},
    }
    task = MozLintTask("lintTaskId", task_status)

    # Load artifact related to that bug
    path = os.path.join(FIXTURES_DIR, "mozlint_license_no_check.json")
    with open(path) as f:
        issues = task.parse_issues(
            {"public/code-review/mozlint": json.load(f)}, mock_revision
        )

    # Check the issue
    assert len(issues) == 1
    issue = issues.pop()
    assert (
        str(issue)
        == "source-test-mozlint-license issue source-test-mozlint-license@error intl/locale/rust/unic-langid-ffi/src/lib.rs full file"
    )
    assert issue.check == issue.analyzer.name == "source-test-mozlint-license"
    assert issue.build_hash() == "7142c536e10b31925b018c37b0e6f9f8"
