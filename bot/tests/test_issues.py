# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import hashlib

import pytest

from code_review_bot.tasks.base import AnalysisTask
from code_review_bot.tasks.clang_format import ClangFormatIssue
from code_review_bot.tasks.lint import MozLintIssue


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


def test_build_hash(mock_revision, mock_hgmo):
    """
    Test build hash algorithm
    """
    # Hardcode revision & repo
    mock_revision.repository = "test-try"
    mock_revision.mercurial_revision = "deadbeef1234"

    issue = MozLintIssue(
        "mock-analyzer-eslint",
        "path/to/file.cpp",
        42,
        "error",
        123,
        "eslint",
        "A random & fake linting issue",
        "EXXX",
        mock_revision,
    )
    assert (
        str(issue) == "mock-analyzer-eslint issue EXXX@error path/to/file.cpp line 123"
    )

    # Check the mock file retrieval for that file
    raw_file = mock_revision.load_file(issue.path)
    assert raw_file == "\n".join(
        f"test-try:deadbeef1234:path/to/file.cpp:{i+1}" for i in range(1000)
    )

    # Build hash in the unit test by re-creating the payload
    payload = "mock-analyzer-eslint:path/to/file.cpp:error:EXXX:{}:test-try:deadbeef1234:path/to/file.cpp:123"
    hash_check = hashlib.md5(payload.encode("utf-8")).hexdigest()
    assert hash_check == "045f57ef8ee111d0c8c475bd7a617564" == issue.build_hash()
