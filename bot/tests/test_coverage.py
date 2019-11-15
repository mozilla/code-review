# -*- coding: utf-8 -*-
from code_review_bot.tasks.coverage import ZeroCoverageTask


def test_coverage(mock_config, mock_revision, mock_coverage_artifact, mock_hgmo):
    task_status = {"task": {}, "status": {}}
    cov = ZeroCoverageTask("covTaskId", task_status)

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
        "hash": "c64ebc6d4a3297b192364db4b022e5e2",
    }
    assert issue.as_phabricator_lint() == {
        "code": "coverage",
        "line": 1,
        "name": "This file is uncovered",
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
        "hash": "0cbf1c1105c3b06ea9e8067a50a7e2f6",
    }
    assert issue.as_phabricator_lint() == {
        "code": "coverage",
        "line": 1,
        "name": "This file is uncovered",
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
        "hash": "9319c5bebc687cb439302ca049a9bff7",
    }
    assert issue.as_phabricator_lint() == {
        "code": "coverage",
        "line": 1,
        "name": "This file is uncovered",
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
