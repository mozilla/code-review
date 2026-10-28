# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os

import pytest
from conftest import FIXTURES_DIR

from code_review_bot.tasks.lint import MozLintIssue, MozLintTask, parse_line_range


def test_flake8_checks(mock_config, mock_revision, mock_hgmo, mock_task):
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
        mock_revision,
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
        mock_revision,
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
        "hash": "d8deb1271c70950549ec8cf49a4623ac",
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

    assert issue.as_phabricator_issue() == {
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
        "hash": "15cf70b31f0a6cd0a3a6914f0e4b8900",
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
    assert issue.hash == "7142c536e10b31925b018c37b0e6f9f8"


@pytest.mark.parametrize(
    "lineno, lineoffset, expected",
    [
        (10, None, (10, 1)),
        ("10", None, (10, 1)),
        (None, 3, (0, 1)),
        # Flat integer, as used by ruff, clippy, compare-locales
        (10, 0, (10, 1)),
        (10, 3, (10, 4)),
        (10, "3", (10, 4)),
        # Tuple as documented by mozlint: (<lineno offset>, <num lines>)
        (10, [0, 4], (10, 4)),
        (10, (2, 3), (10, 5)),
        (10, [-2, 3], (8, 3)),
        # Invalid values fall back to a single line
        (10, "invalid", (10, 1)),
        (10, [1, 2, 3], (10, 1)),
    ],
)
def test_parse_line_range(lineno, lineoffset, expected):
    assert parse_line_range(lineno, lineoffset) == expected


def test_lineoffset(mock_config, mock_revision, mock_hgmo, mock_task):
    """
    Check that multi-line mozlint issues are matched against the patch
    on their whole range, not only on the first line
    """
    task_status = {
        "task": {"metadata": {"name": "source-test-mozlint-l10n"}},
        "status": {},
    }
    task = MozLintTask("lintTaskId", task_status)
    issue_payload = {
        "path": "/builds/worker/checkouts/gecko/test.ftl",
        "relpath": "test.ftl",
        "column": 1,
        "level": "warning",
        "lineno": 10,
        "lineoffset": 3,
        "linter": "l10n",
        "message": "Dummy multiline warning",
        "rule": "dummy",
    }
    issues = task.parse_issues(
        {"public/code-review/mozlint.json": {"test.ftl": [issue_payload]}},
        mock_revision,
    )
    assert len(issues) == 1
    issue = issues[0]
    assert issue.line == 10
    assert issue.nb_lines == 4

    # Only the last line of the entity is modified
    mock_revision.lines = {"test.ftl": [13]}
    assert mock_revision.contains(issue)
    mock_revision.lines = {"test.ftl": [14]}
    assert not mock_revision.contains(issue)
