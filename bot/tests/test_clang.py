# -*- coding: utf-8 -*-
import os.path

import pytest

from code_review_bot.tasks.clang_format import ClangFormatTask
from code_review_bot.tasks.clang_tidy import ClangTidyIssue, ClangTidyTask
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
    from code_review_bot import Level, Reliability

    issue = ClangTidyIssue(
        mock_task(ClangTidyTask, "clang-tidy"),
        mock_revision,
        "test.cpp",
        "42",
        "51",
        "dummy-check",
        "dummy message withUppercaseChars",
        Level.Warning,
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
        "hash": "89cc9f47b63f3184d0914797ca740b9b",
        "fix": None,
    }


def test_as_markdown(mock_revision, mock_task):
    """
    Test markdown generation for ClangTidyIssue
    """
    from code_review_bot import Level, Reliability

    issue = ClangTidyIssue(
        mock_task(ClangTidyTask, "clang-tidy"),
        mock_revision,
        "test.cpp",
        "42",
        "51",
        "dummy-check",
        "dummy message",
        Level.Warning,
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


def test_real_patch(mock_revision, mock_task):
    """
    Test clang format patch parsing with a real patch
    """
    task = mock_task(ClangFormatTask, "mock-clang-format")

    with open(os.path.join(FIXTURES_DIR, "clang_format.diff")) as f:
        artifact = f.read()

    issues = task.parse_issues(
        {"public/code-review/clang-format.diff": artifact}, mock_revision
    )

    assert len(issues) == 3

    assert [i.as_dict() for i in issues] == [
        {
            "analyzer": "mock-clang-format",
            "check": "invalid-styling",
            "column": None,
            "fix": """    CGFontRef aCGFont, const RefPtr<UnscaledFont>& aUnscaledFont, Float aSize,
    const DeviceColor& aFontSmoothingBackgroundColor, bool aUseFontSmoothing,
    bool aApplySyntheticBold) {
  return MakeAndAddRef<ScaledFontMac>(aCGFont, aUnscaledFont, aSize, false,
                                      aFontSmoothingBackgroundColor,
                                      aUseFontSmoothing, aApplySyntheticBold);
}
#endif""",
            "hash": None,
            "in_patch": False,
            "level": "warning",
            "line": 616,
            "message": "The change does not follow the C/C++ coding style, please reformat",
            "nb_lines": 4,
            "path": "gfx/2d/Factory.cpp",
            "publishable": False,
            "validates": False,
        },
        {
            "analyzer": "mock-clang-format",
            "check": "invalid-styling",
            "column": None,
            "fix": """  } else {
    // Comment to trigger readability-else-after-return
    const auto x = "aa";
  }
  return true;
}""",
            "hash": None,
            "in_patch": False,
            "level": "warning",
            "line": 118,
            "message": "The change does not follow the C/C++ coding style, please reformat",
            "nb_lines": 6,
            "path": "dom/canvas/ClientWebGLContext.cpp",
            "publishable": False,
            "validates": True,
        },
        {
            "analyzer": "mock-clang-format",
            "check": "invalid-styling",
            "column": None,
            "fix": """  if (false) return true;
  return eNameOK;
}""",
            "hash": None,
            "in_patch": False,
            "level": "warning",
            "line": 36,
            "message": "The change does not follow the C/C++ coding style, please reformat",
            "nb_lines": 3,
            "path": "accessible/xul/XULAlertAccessible.cpp",
            "publishable": False,
            "validates": False,
        },
    ]
