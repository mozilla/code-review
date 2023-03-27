# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest

from code_review_bot import Level
from code_review_bot.tasks.default import DefaultIssue
from code_review_bot.tasks.default import DefaultTask


@pytest.mark.parametrize(
    "path, matches",
    [
        ("public/code-review/issues.json", True),
        ("private/code-review/issues.json", False),
        ("public/code-review/mozlint.json", False),
    ],
)
def test_matches(path, matches, mock_taskcluster_config):
    """Test that DefaultTask matches tasks with valid artifacts"""

    queue = mock_taskcluster_config.get_service("queue")
    queue.configure(
        {
            "testDefaultTask": {
                "name": "some-analyzer",
                "state": "failed",
                "artifacts": {path: {}},
            }
        }
    )
    assert DefaultTask.matches("testDefaultTask") is matches


def test_parser(mock_workflow, mock_revision, mock_hgmo, mock_backend):
    """Test the default format parser"""
    mock_workflow.setup_mock_tasks(
        {
            "remoteTryTask": {"dependencies": ["analyzer-A", "analyzer-B"]},
            "analyzer-A": {},
            "analyzer-B": {
                "name": "any-analyzer-name",
                "state": "failed",
                "artifacts": {
                    "nope.log": "No issues here !",
                    "still-nope.txt": "xxxxx",
                    "public/code-review/issues.json": {
                        "test.cpp": [
                            {
                                "path": "test.cpp",
                                "line": 42,
                                "column": 51,
                                "level": "error",
                                "check": "XYZ",
                                "message": "A random issue happened here",
                            }
                        ]
                    },
                },
            },
            "extra-task": {},
        }
    )
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 1
    issue = issues.pop()

    assert isinstance(issue, DefaultIssue)
    assert str(issue) == "any-analyzer-name issue XYZ@error test.cpp line 42"
    assert issue.path == "test.cpp"
    assert issue.line == 42
    assert issue.nb_lines == 1
    assert issue.column == 51
    assert issue.level == Level.Error
    assert issue.check == "XYZ"
    assert issue.message == "A random issue happened here"
    assert issue.as_text() == "Error: A random issue happened here [XYZ]"
    assert (
        issue.as_markdown()
        == """
## issue any-analyzer-name

- **Path**: test.cpp
- **Level**: error
- **Check**: XYZ
- **Line**: 42
- **Publishable**: yes

```
A random issue happened here
```
"""
    )

    assert issue.build_hash() == "533d1aefc79ef542b3e7d677c1c5724e"
    assert issue.as_dict() == {
        "analyzer": "any-analyzer-name",
        "check": "XYZ",
        "column": 51,
        "hash": "533d1aefc79ef542b3e7d677c1c5724e",
        "in_patch": False,
        "level": "error",
        "line": 42,
        "message": "A random issue happened here",
        "nb_lines": 1,
        "path": "test.cpp",
        "publishable": True,
        "validates": True,
        "fix": None,
    }
