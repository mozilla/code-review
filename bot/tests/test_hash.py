# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import hashlib

import pytest

from code_review_bot.tasks.lint import MozLintIssue, MozLintTask


def test_build_hash(mock_revision, mock_hgmo, mock_task):
    """
    Test build hash algorithm
    """
    # Hardcode revision & repo
    mock_revision.head_repository = "test-try"
    mock_revision.head_changeset = "deadbeef1234"

    issue = MozLintIssue(
        mock_task(MozLintTask, "mock-analyzer-eslint"),
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
    payload = (
        "mock-analyzer-eslint:"
        "path/to/file.cpp:error:"
        "EXXX:"
        "{}:"
        "test-try:deadbeef1234:"
        "path/to/file.cpp:"
        "123:"
        "A random & fake linting issue"
    )
    hash_check = hashlib.md5(payload.encode("utf-8")).hexdigest()
    assert hash_check == "b06e5b92a609496d1473ca90fec1749c" == issue.build_hash()


def test_indentation_effect(mock_revision, mock_hgmo, mock_task):
    """
    Test indentation does not affect the hash
    2 lines with same content in a file, triggering the same error
    should produce the same hash
    """
    # Hardcode revision & repo
    mock_revision.head_repository = "test-try"
    mock_revision.head_changeset = "deadbeef1234"

    issue_indent = MozLintIssue(
        mock_task(MozLintTask, "mock-analyzer-flake8"),
        "hello1",
        2,
        "error",
        1,
        "flake8",
        "A random & fake linting issue",
        "EXXX",
        mock_revision,
    )
    issue_no_indent = MozLintIssue(
        mock_task(MozLintTask, "mock-analyzer-flake8"),
        "hello1",
        5,
        "error",
        1,
        "flake8",
        "A random & fake linting issue",
        "EXXX",
        mock_revision,
    )

    # Check raw file content
    lines = mock_revision.load_file("hello1").splitlines()
    assert lines[1] == '    print("Hello !")'
    assert lines[4] == 'print("Hello !")'

    # Check the hashes are equal
    assert (
        issue_indent.build_hash()
        == issue_no_indent.build_hash()
        == "a8c5c52b21c12b483617adc60cdd5dc2"
    )


def test_full_file(mock_revision, mock_hgmo, mock_task):
    """
    Test build hash algorithm when using a full file (line is -1)
    """
    # Hardcode revision & repo
    mock_revision.head_repository = "test-try"
    mock_revision.head_changeset = "deadbeef1234"

    issue = MozLintIssue(
        mock_task(MozLintTask, "mock-analyzer-fullfile"),
        "path/to/afile.py",
        0,
        "error",
        -1,
        "fullfile",
        "Some issue found on a file",
        "EXXX",
        mock_revision,
    )
    assert (
        str(issue)
        == "mock-analyzer-fullfile issue EXXX@error path/to/afile.py full file"
    )
    assert issue.line is None

    # Build hash should use the full file
    assert issue.build_hash() == "65fe9040e64b3617e4cbf40ef478f62d"

    # Check positive integers or None are used in report
    assert issue.as_dict() == {
        "analyzer": "mock-analyzer-fullfile",
        "check": "EXXX",
        "column": 0,
        "hash": "65fe9040e64b3617e4cbf40ef478f62d",
        "in_patch": False,
        "level": "error",
        "line": None,
        "message": "Some issue found on a file",
        "nb_lines": 1,
        "path": "path/to/afile.py",
        "publishable": True,
        "validates": True,
        "fix": None,
    }


@pytest.mark.parametrize("path", [".", "..", "a/../../b"])
def test_incorrect_file_path(mock_revision, path):
    """
    Test that a revision raises a ValueError when loading
    a file with a path pointing outside the repository
    """
    with pytest.raises(ValueError):
        mock_revision.load_file(path)
