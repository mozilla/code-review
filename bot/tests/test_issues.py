# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest

from code_review_bot.tasks.base import AnalysisTask
from code_review_bot.tasks.clang_format import ClangFormatIssue


def test_allowed_paths(mock_config):
    """
    Test allowed paths for ClangFormatIssue
    The test config has these 2 rules: dom/* and tests/*.py
    """

    def _allowed(path):
        # Build an issue and check its validation
        # that will trigger the path validation
        issue = ClangFormatIssue(path, 1, 1, None)
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


@pytest.mark.parametrize(
    "path, cleaned_path",
    [
        ("myfile.cpp", "myfile.cpp"),
        # Unknown full path
        ("/absolute/path/file.rs", "/absolute/path/file.rs"),
        # Known full paths
        ("/builds/worker/checkouts/gecko/js/xx.h", "js/xx.h"),
        ("/home/worker/nss/something.py", "something.py"),
        ("/home/worker/nspr/Test.c", "Test.c"),
    ],
)
def test_cleaned_paths(log, path, cleaned_path):
    """
    Test cleaning a path using a known worker's checkout
    """
    assert len(log.events) == 0

    task = AnalysisTask(
        "testTask", {"task": {"metadata": {"name": "test-task"}}, "status": None}
    )
    assert task.clean_path(path) == cleaned_path

    # Check a warning is sent when path is cleaned
    if path == cleaned_path:
        assert len(log.events) == 0
    else:
        assert len(log.events) == 1
        assert log.has(
            "Cleaned issue absolute path", path=path, name="test-task", level="warning"
        )
