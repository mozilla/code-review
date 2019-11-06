# -*- coding: utf-8 -*-
import json
import os

import pytest

from code_review_bot.tasks.infer import InferIssue
from code_review_bot.tasks.infer import InferTask
from conftest import FIXTURES_DIR


def test_as_text(mock_revision):
    """
    Test text export for InferIssue
    """
    parts = {
        "file": "path/to/file.java",
        "line": 3,
        "column": -1,
        "bug_type": "SOMETYPE",
        "kind": "SomeKindOfBug",
        "qualifier": "Error on this line",
    }
    issue = InferIssue("mock-infer", parts, mock_revision)

    expected = "SomeKindOfBug: Error on this line [infer: SOMETYPE]"
    assert issue.as_text() == expected


def test_as_dict(mock_revision, mock_hgmo):
    """
    Test dict export for InferIssue
    """

    parts = {
        "file": "path/to/file.java",
        "line": 3,
        "column": -1,
        "bug_type": "SOMETYPE",
        "kind": "SomeKindOfBug",
        "qualifier": "Error on this line",
    }
    issue = InferIssue("mock-infer", parts, mock_revision)

    assert issue.as_dict() == {
        "analyzer": "mock-infer",
        "check": "SOMETYPE",
        "column": -1,
        "in_patch": False,
        "level": "SomeKindOfBug",
        "line": 3,
        "message": "Error on this line",
        "nb_lines": 1,
        "path": "path/to/file.java",
        "publishable": False,
        "validates": True,
        "hash": "405fafd74d01b0d109903804e6cf3a5a",
    }


def test_as_markdown(mock_revision):
    """
    Test markdown generation for InferIssue
    """

    parts = {
        "file": "path/to/file.java",
        "line": 3,
        "column": -1,
        "bug_type": "SOMETYPE",
        "kind": "SomeKindOfBug",
        "qualifier": "Error on this line",
    }
    issue = InferIssue("mock-infer", parts, mock_revision)

    assert (
        issue.as_markdown()
        == """
## infer error

- **Message**: Error on this line
- **Location**: path/to/file.java:3:-1
- **In patch**: no
- **Infer check**: SOMETYPE
- **Publishable **: no
"""
    )


@pytest.mark.parametrize("version, nb", [("0.16.0", 9), ("0.17.0", 32)])
def test_infer_artifact(version, nb, mock_revision, mock_hgmo):
    """
    Test Infer artifact per version, comparing a raw artifact processed
    and expected issues list
    """
    with open(os.path.join(FIXTURES_DIR, f"infer_artifact_{version}.json")) as f:
        artifact = json.load(f)

    status = {"task": {"metadata": {"name": "mock-infer"}}, "status": {}}
    task = InferTask("someTaskId", status)
    issues = task.parse_issues(
        {"public/code-review/infer.json": artifact}, mock_revision
    )

    assert len(artifact) == len(issues) == nb

    issues_data = [issue.as_dict() for issue in issues]

    with open(os.path.join(FIXTURES_DIR, f"infer_issues_{version}.json")) as f:
        assert issues_data == json.load(f)
