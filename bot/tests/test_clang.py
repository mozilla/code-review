# -*- coding: utf-8 -*-


def test_expanded_macros(mock_revision):
    """
    Test expanded macros are detected by clang issue
    """
    from code_review_bot.tasks.clang_tidy import ClangTidyIssue

    issue = ClangTidyIssue(
        mock_revision, "test.cpp", "42", "51", "dummy message", "dummy-check", "error"
    )
    assert issue.is_problem()
    assert issue.line == 42
    assert issue.char == 51
    assert issue.notes == []
    assert issue.is_expanded_macro() is False

    # Add a note starting with "expanded from macro..."
    issue.notes.append(
        ClangTidyIssue(
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
        mock_revision,
        "test.cpp",
        "42",
        "51",
        "dummy-check",
        "dummy message withUppercaseChars",
        "error",
    )
    issue.body = "Dummy body withUppercaseChars"

    assert (
        issue.as_text()
        == "Error: Dummy message withUppercaseChars [clang-tidy: dummy-check]\n```\nDummy body withUppercaseChars\n```"
    )


def test_as_dict(mock_revision):
    """
    Test text export for ClangTidyIssue
    """
    from code_review_bot import Reliability
    from code_review_bot.tasks.clang_tidy import ClangTidyIssue

    issue = ClangTidyIssue(
        mock_revision,
        "test.cpp",
        "42",
        "51",
        "dummy-check",
        "dummy message withUppercaseChars",
        "error",
        Reliability.Low,
    )
    issue.body = "Dummy body withUppercaseChars"

    assert issue.as_dict() == {
        "analyzer": "clang-tidy",
        "path": "test.cpp",
        "line": 42,
        "nb_lines": 1,
        "char": 51,
        "check": "dummy-check",
        "level": "error",
        "message": "dummy message withUppercaseChars",
        "body": "Dummy body withUppercaseChars",
        "reason": None,
        "notes": [],
        "validation": {"publishable_check": False, "is_expanded_macro": False},
        "in_patch": False,
        "is_new": False,
        "validates": False,
        "publishable": False,
        "reliability": "low",
    }


def test_as_markdown(mock_revision):
    """
    Test markdown generation for ClangTidyIssue
    """
    from code_review_bot import Reliability
    from code_review_bot.tasks.clang_tidy import ClangTidyIssue

    issue = ClangTidyIssue(
        mock_revision,
        "test.cpp",
        "42",
        "51",
        "dummy-check",
        "dummy message",
        "error",
        Reliability.High,
    )
    issue.body = "Dummy body"

    assert (
        issue.as_markdown()
        == """
## clang-tidy error

- **Message**: dummy message
- **Location**: test.cpp:42:51
- **In patch**: no
- **Clang check**: dummy-check
- **Publishable check**: no
- **Expanded Macro**: no
- **Publishable **: no
- **Is new**: no
- **Checker reliability **: high (false positive risk)

```
Dummy body
```


"""
    )
    assert issue.as_phabricator_lint() == {
        "char": 51,
        "code": "clang-tidy.dummy-check",
        "line": 42,
        "name": "Clang-Tidy - dummy-check",
        "description": "dummy message\nChecker reliability is high, meaning that the false positive ratio is low.\n\n > Dummy body",
        "path": "test.cpp",
        "severity": "warning",
    }
