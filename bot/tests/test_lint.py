# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


def test_flake8_checks(mock_config, mock_revision, mock_hgmo):
    """
    Check flake8 check detection
    """
    from code_review_bot.tasks.lint import MozLintIssue

    # Valid issue
    issue = MozLintIssue(
        "mock-lint-flake8",
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
        "mock-lint-flake8",
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
        "is_new": False,
        "level": "error",
        "line": 1,
        "message": "Remove bad quotes or whatever.",
        "nb_lines": 1,
        "path": "test.py",
        "publishable": False,
        "validates": False,
        "hash": "57a49008d6a3ec23f987c0bf62c43d75",
    }


def test_as_text(mock_config, mock_revision, mock_hgmo):
    """
    Test text export for ClangTidyIssue
    """
    from code_review_bot.tasks.lint import MozLintIssue

    issue = MozLintIssue(
        "mock-lint-flake8",
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
        "code": "flake8.dummy rule",
        "line": 1,
        "name": "MozLint Flake8 - dummy rule",
        "description": "dummy test withUppercaseChars",
        "path": "test.py",
        "severity": "error",
    }

    assert issue.as_dict() == {
        "analyzer": "mock-lint-flake8",
        "check": "dummy rule",
        "column": 1,
        "in_patch": False,
        "is_new": False,
        "level": "error",
        "line": 1,
        "message": "dummy test withUppercaseChars",
        "nb_lines": 1,
        "path": "test.py",
        "publishable": False,
        "validates": True,
        "hash": "34c27d119c21ea5a2cd3f6ac230d8c4e",
    }
