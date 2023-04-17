# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from code_review_bot.tasks.clang_format import ClangFormatIssue, ClangFormatTask


def test_allowed_paths(mock_config, mock_revision, mock_task):
    """
    Test allowed paths for ClangFormatIssue
    The test config has these 2 rules: dom/* and tests/*.py
    """

    def _allowed(path):
        # Build an issue and check its validation
        # that will trigger the path validation
        lines = [
            (1, None, b"deletion"),
            (None, 1, b"change here"),
        ]
        issue = ClangFormatIssue(
            mock_task(ClangFormatTask, "mock-clang-format"), path, lines, mock_revision
        )
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


def test_backend_publication(mock_revision, mock_task):
    """
    Test the backend publication status modifies an issue publication
    """

    lines = [
        (1, None, b"deletion"),
        (None, 1, b"change here"),
    ]
    issue = ClangFormatIssue(
        mock_task(ClangFormatTask, "mock-clang-format"),
        "dom/somefile.cpp",
        lines,
        mock_revision,
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
