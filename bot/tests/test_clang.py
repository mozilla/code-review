# -*- coding: utf-8 -*-


def test_expanded_macros(mock_revision):
    """
    Test expanded macros are detected by clang issue
    """
    from code_review_bot.tasks.clang_tidy import ClangTidyIssue

    issue = ClangTidyIssue(
        "clang-tidy",
        mock_revision,
        "test.cpp",
        "42",
        "51",
        "dummy message",
        "dummy-check",
        "error",
    )
    assert issue.is_problem()
    assert issue.line == 42
    assert issue.column == 51
    assert issue.notes == []
    assert issue.is_expanded_macro() is False

    # Add a note starting with "expanded from macro..."
    issue.notes.append(
        ClangTidyIssue(
            "clang-tidy",
            mock_revision,
            "test.cpp",
            "42",
            "51",
            "dummy-check-note",
            "expanded from macro Blah dummy.cpp",
            "note",
        )
    )
    assert issue.is_expanded_macro() is True

    # Add another note does not change it
    issue.notes.append(
        ClangTidyIssue(
            "clang-tidy",
            mock_revision,
            "test.cpp",
            "42",
            "51",
            "dummy-check-note",
            "This is not an expanded macro",
            "note",
        )
    )
    assert issue.is_expanded_macro() is True

    # But if we swap them, it does not work anymore
    issue.notes.reverse()
    assert issue.is_expanded_macro() is False


def test_as_text(mock_revision):
    """
    Test text export for ClangTidyIssue
    """
    from code_review_bot.tasks.clang_tidy import ClangTidyIssue

    issue = ClangTidyIssue(
        "clang-tidy",
        mock_revision,
        "test.cpp",
        "42",
        "51",
        "dummy-check",
        "dummy message withUppercaseChars",
        "error",
    )

    assert (
        issue.as_text()
        == "Error: Dummy message withUppercaseChars [clang-tidy: dummy-check]"
    )


def test_as_dict(mock_revision):
    """
    Test text export for ClangTidyIssue
    """
    from code_review_bot import Reliability
    from code_review_bot.tasks.clang_tidy import ClangTidyIssue

    issue = ClangTidyIssue(
        "clang-tidy",
        mock_revision,
        "test.cpp",
        "42",
        "51",
        "dummy-check",
        "dummy message withUppercaseChars",
        "error",
        Reliability.Low,
    )

    assert issue.as_dict() == {
        "analyzer": "clang-tidy",
        "path": "test.cpp",
        "line": 42,
        "nb_lines": 1,
        "column": 51,
        "check": "dummy-check",
        "level": "error",
        "message": "dummy message withUppercaseChars",
        "in_patch": False,
        "is_new": False,
        "validates": True,
        "publishable": False,
        "extras": {"notes": [], "reason": None, "reliability": "low"},
    }


def test_as_markdown(mock_revision):
    """
    Test markdown generation for ClangTidyIssue
    """
    from code_review_bot import Reliability
    from code_review_bot.tasks.clang_tidy import ClangTidyIssue

    issue = ClangTidyIssue(
        "clang-tidy",
        mock_revision,
        "test.cpp",
        "42",
        "51",
        "dummy-check",
        "dummy message",
        "error",
        Reliability.High,
    )

    assert (
        issue.as_markdown()
        == """
## clang-tidy error

- **Message**: dummy message
- **Location**: test.cpp:42:51
- **In patch**: no
- **Clang check**: dummy-check
- **Publishable check**: yes
- **Expanded Macro**: no
- **Publishable **: no
- **Is new**: no
- **Checker reliability **: high (false positive risk)


"""
    )
    assert issue.as_phabricator_lint() == {
        "char": 51,
        "code": "clang-tidy.dummy-check",
        "line": 42,
        "name": "Clang-Tidy - dummy-check",
        "description": "dummy message\nChecker reliability is high, meaning that the false positive ratio is low.",
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
