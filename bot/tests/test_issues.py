# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os

import pytest

from code_review_bot import Level
from code_review_bot.tasks.clang_format import ClangFormatIssue
from code_review_bot.tasks.lint import MozLintTask
from conftest import FIXTURES_DIR


def test_allowed_paths(mock_config, mock_revision):
    """
    Test allowed paths for ClangFormatIssue
    The test config has these 2 rules: dom/* and tests/*.py
    """

    def _allowed(path):
        # Build an issue and check its validation
        # that will trigger the path validation
        issue = ClangFormatIssue("mock-clang-format", path, 1, 1, mock_revision)
        return issue.validates()

    checks = {
        "nope.cpp": False,
        "dom/whatever.cpp": True,
        "dom/sub/folders/whatever.cpp": True,
        "dom/noext": True,
        "dom_fail.h": False,
        "tests/xxx.pyc": False,
        "tests/folder/part/1.py": True,
    }
    for path, result in checks.items():
        assert _allowed(path) is result


def test_backend_publication(mock_revision):
    """
    Test the backend publication status modifies an issue publication
    """

    issue = ClangFormatIssue(
        "mock-clang-format", "dom/somefile.cpp", 1, 1, mock_revision
    )
    assert issue.validates()

    # At first backend data is empty
    assert issue.on_backend is None

    # Not publishable as not in patch
    assert mock_revision.lines == {}
    assert not mock_revision.contains(issue)
    assert not issue.is_publishable()

    # The backend data takes precedence over local in patch
    issue.on_backend = {"publishable": True}
    assert issue.is_publishable()


@pytest.mark.parametrize(
    "tier_level, issue_level",
    [
        (None, Level.Warning),
        ("1", Level.Error),
        (1, Level.Error),
        ("2", Level.Warning),
        (2, Level.Warning),
        ("3", Level.Warning),
        (3, Level.Warning),
        ("anything else", Level.Warning),
    ],
)
def test_tier_level(tier_level, issue_level, mock_revision):
    """
    Test a task tier level on treeherder modifies the level of the issue
    Warnings must become Errors on tier 1 tasks
    """
    mock_revision.repository = "test-try"
    mock_revision.mercurial_revision = "deadbeef1234"
    task_status = {
        "task": {"metadata": {"name": "source-test-mozlint-fake"}},
        "status": {},
    }

    # Apply treeherder level
    if tier_level:
        task_status["task"].update({"extra": {"treeherder": {"tier": tier_level}}})

    task = MozLintTask("lintTaskId", task_status)

    # Load artifact related to that bug
    path = os.path.join(FIXTURES_DIR, "mozlint_warnings.json")
    with open(path) as f:
        issues = task.parse_issues(
            {"public/code-review/mozlint": json.load(f)}, mock_revision
        )

    # We should have 2 issues that use the correct level
    assert len(issues) == 2
    assert {i.level for i in issues} == {issue_level}
