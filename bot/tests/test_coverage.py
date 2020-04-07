# -*- coding: utf-8 -*-
from code_review_bot.tasks.coverage import ZeroCoverageTask


def test_coverage(
    mock_config, mock_revision, mock_coverage_artifact, mock_hgmo, mock_task
):
    cov = mock_task(ZeroCoverageTask, "coverage")

    mock_revision.files = [
        # Uncovered file
        "my/path/file1.cpp",
        # Covered file
        "my/path/file2.js",
        # Uncovered third-party file
        "test/dummy/thirdparty.c",
        # Uncovered header file
        "my/path/header.h",
    ]

    # Build fake lines.
    for path in mock_revision.files:
        mock_revision.lines[path] = [0]

    issues = cov.parse_issues(mock_coverage_artifact, mock_revision)

    # The list must have three elements
    assert len(issues) == 3

    # Verify that each element has a sane value
    issue = issues[0]
    assert issue.path == "my/path/file1.cpp"
    assert issue.line is None
    assert issue.message == "This file is uncovered"
    assert (
        str(issue) == "coverage issue no-coverage@warning my/path/file1.cpp full file"
    )

    assert issue.validates()

    assert issue.as_dict() == {
        "analyzer": "coverage",
        "path": "my/path/file1.cpp",
        "line": None,
        "message": "This file is uncovered",
        "in_patch": True,
        "validates": True,
        "publishable": True,
        "check": "no-coverage",
        "column": None,
        "level": "warning",
        "nb_lines": 1,
        "hash": "35268931247f488cf2a71d0b06285e76",
        "fix": None,
    }
    assert issue.as_phabricator_lint() == {
        "code": "no-coverage",
        "line": 1,
        "name": "code coverage analysis",
        "description": "WARNING: This file is uncovered",
        "path": "my/path/file1.cpp",
        "severity": "warning",
    }
    assert issue.as_text() == "This file is uncovered"
    assert (
        issue.as_markdown()
        == """
## coverage problem

- **Path**: my/path/file1.cpp
- **Publishable**: yes

```
This file is uncovered
```
"""
    )

    issue = issues[1]
    assert issue.path == "test/dummy/thirdparty.c"
    assert issue.line is None
    assert issue.message == "This file is uncovered"
    assert (
        str(issue)
        == "coverage issue no-coverage@warning test/dummy/thirdparty.c full file"
    )

    assert issue.validates()

    assert issue.as_dict() == {
        "analyzer": "coverage",
        "path": "test/dummy/thirdparty.c",
        "line": None,
        "message": "This file is uncovered",
        "in_patch": True,
        "validates": True,
        "publishable": True,
        "check": "no-coverage",
        "column": None,
        "level": "warning",
        "nb_lines": 1,
        "hash": "a864bee7b5876989534b28cf245e2ee0",
        "fix": None,
    }
    assert issue.as_phabricator_lint() == {
        "code": "no-coverage",
        "line": 1,
        "name": "code coverage analysis",
        "description": "WARNING: This file is uncovered",
        "path": "test/dummy/thirdparty.c",
        "severity": "warning",
    }
    assert issue.as_text() == "This file is uncovered"
    assert (
        issue.as_markdown()
        == """
## coverage problem

- **Path**: test/dummy/thirdparty.c
- **Publishable**: yes

```
This file is uncovered
```
"""
    )

    issue = issues[2]
    assert issue.path == "my/path/header.h"
    assert issue.line is None
    assert issue.message == "This file is uncovered"
    assert str(issue) == "coverage issue no-coverage@warning my/path/header.h full file"

    assert not issue.validates()

    assert issue.as_dict() == {
        "analyzer": "coverage",
        "path": "my/path/header.h",
        "line": None,
        "message": "This file is uncovered",
        "in_patch": True,
        "validates": False,
        "publishable": False,
        "check": "no-coverage",
        "column": None,
        "level": "warning",
        "nb_lines": 1,
        "hash": "8d06f3f7063ff4ba9f42b9fe2a808dbd",
        "fix": None,
    }
    assert issue.as_phabricator_lint() == {
        "code": "no-coverage",
        "line": 1,
        "name": "code coverage analysis",
        "description": "WARNING: This file is uncovered",
        "path": "my/path/header.h",
        "severity": "warning",
    }
    assert issue.as_text() == "This file is uncovered"
    assert (
        issue.as_markdown()
        == """
## coverage problem

- **Path**: my/path/header.h
- **Publishable**: no

```
This file is uncovered
```
"""
    )
