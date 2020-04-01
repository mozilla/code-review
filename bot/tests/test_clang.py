# -*- coding: utf-8 -*-
import json
import os.path

import pytest

from code_review_bot.tasks.clang_format import ClangFormatTask
from code_review_bot.tasks.clang_tidy import ClangTidyIssue
from code_review_bot.tasks.clang_tidy import ClangTidyTask
from conftest import FIXTURES_DIR


def test_expanded_macros(mock_revision, mock_task):
    """
    Test expanded macros are detected by clang issue
    """
    analyzer = mock_task(ClangTidyTask, "clang-tidy")
    issue = ClangTidyIssue(
        analyzer, mock_revision, "test.cpp", "42", "51", "dummy message", "dummy-check"
    )
    assert issue.line == 42
    assert issue.column == 51
    assert issue.notes == []
    assert issue.is_expanded_macro() is False

    # Add a note starting with "expanded from macro..."
    issue.notes.append(
        ClangTidyIssue(
            analyzer,
            mock_revision,
            "test.cpp",
            "42",
            "51",
            "dummy-check-note",
            "expanded from macro Blah dummy.cpp",
        )
    )
    assert issue.is_expanded_macro() is True

    # Add another note does not change it
    issue.notes.append(
        ClangTidyIssue(
            analyzer,
            mock_revision,
            "test.cpp",
            "42",
            "51",
            "dummy-check-note",
            "This is not an expanded macro",
        )
    )
    assert issue.is_expanded_macro() is True

    # But if we swap them, it does not work anymore
    issue.notes.reverse()
    assert issue.is_expanded_macro() is False


def test_as_text(mock_revision, mock_task):
    """
    Test text export for ClangTidyIssue
    """

    issue = ClangTidyIssue(
        mock_task(ClangTidyTask, "clang-tidy"),
        mock_revision,
        "test.cpp",
        "42",
        "51",
        "dummy-check",
        "dummy message withUppercaseChars",
    )

    assert (
        issue.as_text()
        == "Warning: Dummy message withUppercaseChars [clang-tidy: dummy-check]"
    )


def test_as_dict(mock_revision, mock_hgmo, mock_task):
    """
    Test text export for ClangTidyIssue
    """
    from code_review_bot import Reliability

    issue = ClangTidyIssue(
        mock_task(ClangTidyTask, "clang-tidy"),
        mock_revision,
        "test.cpp",
        "42",
        "51",
        "dummy-check",
        "dummy message withUppercaseChars",
        Reliability.Low,
    )

    assert issue.as_dict() == {
        "analyzer": "clang-tidy",
        "path": "test.cpp",
        "line": 42,
        "nb_lines": 1,
        "column": 51,
        "check": "dummy-check",
        "level": "warning",
        "message": "dummy message withUppercaseChars",
        "in_patch": False,
        "validates": True,
        "publishable": False,
        "hash": "f434c3f44cd5da419d9119f504086513",
    }


def test_as_markdown(mock_revision, mock_task):
    """
    Test markdown generation for ClangTidyIssue
    """
    from code_review_bot import Reliability

    issue = ClangTidyIssue(
        mock_task(ClangTidyTask, "clang-tidy"),
        mock_revision,
        "test.cpp",
        "42",
        "51",
        "dummy-check",
        "dummy message",
        Reliability.High,
    )

    assert (
        issue.as_markdown()
        == """
## clang-tidy warning

- **Message**: dummy message
- **Location**: test.cpp:42:51
- **In patch**: no
- **Clang check**: dummy-check
- **Publishable check**: yes
- **Expanded Macro**: no
- **Publishable **: no
- **Checker reliability **: high (false positive risk)


"""
    )
    assert issue.as_phabricator_lint() == {
        "char": 51,
        "code": "dummy-check",
        "line": 42,
        "name": "clang-tidy",
        "description": "WARNING: dummy message",
        "path": "test.cpp",
        "severity": "warning",
    }


def test_settings(mock_config):
    """
    Extensions are hard-coded in settings are
    """
    assert mock_config.app_channel == "test"
    assert mock_config.try_task_id == "remoteTryTask"
    assert mock_config.try_group_id == "remoteTryGroup"
    assert mock_config.cpp_extensions == frozenset(
        [".c", ".cpp", ".cc", ".cxx", ".m", ".mm"]
    )
    assert mock_config.cpp_header_extensions == frozenset([".h", ".hh", ".hpp", ".hxx"])
    assert mock_config.java_extensions == frozenset([".java"])
    assert mock_config.idl_extensions == frozenset([".idl"])
    assert mock_config.js_extensions == frozenset([".js", ".jsm"])


@pytest.mark.parametrize("patch", [b"", b"    ", b"\n", b"  \n  "])
def test_empty_patch(patch):
    """
    Test clang format task detect empty patches
    """
    task_status = {
        "task": {"metadata": {"name": "source-test-clang-format"}},
        "status": {},
    }
    task = ClangFormatTask("someTaskId", task_status)
    patches = task.build_patches(
        {"public/live.log": "some lines", "public/code-review/clang-format.diff": patch}
    )
    assert patches == []


def test_grouping_issues(mock_revision, mock_task, mock_hgmo):
    """
    Test clang format issues group detection
    """
    task = mock_task(ClangFormatTask, "mock-clang-format")

    # This file has 9 issues, some of them are on the same lines
    with open(os.path.join(FIXTURES_DIR, "clang_format_groups.json")) as f:
        artifact = json.load(f)

    issues = task.parse_issues(
        {"public/code-review/clang-format.json": artifact}, mock_revision
    )

    # The parse merge those neighboring issues to only report on relevant groups
    assert len(issues) == 4

    assert [i.as_dict() for i in issues] == [
        {
            "analyzer": "mock-clang-format",
            "check": "invalid-styling",
            "column": 20,
            "hash": "8dab42f345b5d8966e003b77a21fa595",
            "in_patch": False,
            "level": "warning",
            "line": 35,
            "nb_lines": 2,
            "message": """The change does not follow the C/C++ coding style, it must be formatted as:

```
try:deadbeef123456:accessible/xul/XULAlertAccessible.cpp:35
try:deadbeef123456:accessible/xul/XULAlertAccessible.cpp:36
```""",
            "path": "accessible/xul/XULAlertAccessible.cpp",
            "publishable": False,
            "validates": False,
        },
        {
            "analyzer": "mock-clang-format",
            "check": "invalid-styling",
            "column": None,
            "hash": "f9e31e82db2cf57c64593b6c24226bbf",
            "in_patch": False,
            "level": "warning",
            "line": 118,
            "message": """The change does not follow the C/C++ coding style, it must be formatted as:

```
    // Comment to trigger readability-else-after-return
    const auto x = "aa";
  }
```""",
            "nb_lines": 3,
            "path": "dom/canvas/ClientWebGLContext.cpp",
            "publishable": False,
            "validates": True,
        },
        {
            "analyzer": "mock-clang-format",
            "check": "invalid-styling",
            "column": 79,
            "hash": "0f79878d4a5cb7d4c2f233ceafea9d1f",
            "in_patch": False,
            "level": "warning",
            "line": 10,
            "nb_lines": 1,
            "message": """The change does not follow the C/C++ coding style, it must be formatted as:

```
try:deadbeef123456:gfx/2d/Factory.cpp:11
```""",
            "path": "gfx/2d/Factory.cpp",
            "publishable": False,
            "validates": False,
        },
        {
            "analyzer": "mock-clang-format",
            "check": "invalid-styling",
            "column": None,
            "hash": "0f75ebc8d2909eb182d1d90254d1a633",
            "in_patch": False,
            "level": "warning",
            "line": 616,
            "nb_lines": 2,
            "message": """The change does not follow the C/C++ coding style, it must be formatted as:

```
try:deadbeef123456:gfx/2d/Factory.cpp:614
try:deadbeef123456:gfx/2d/Factory.cpp:615
```""",
            "path": "gfx/2d/Factory.cpp",
            "publishable": False,
            "validates": False,
        },
    ]
