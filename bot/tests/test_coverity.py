# -*- coding: utf-8 -*-
import json
import os

from code_review_bot.tasks.coverity import CoverityIssue
from code_review_bot.tasks.coverity import CoverityTask
from code_review_bot.tasks.coverity import Reliability
from conftest import MOCK_DIR


class MockCoverityTask(CoverityTask):
    def __init__(self):
        """
        Simply skip task loading
        """
        self.cleaned_paths = set()
        self.task = {"metadata": {"name": "mock-coverity"}}


def mock_coverity(name):
    """
    Load a Coverity mock file, as a Taskcluster artifact payload
    """
    path = os.path.join(MOCK_DIR, "coverity_{}.json".format(name))
    assert os.path.exists(path), "Missing coverity mock {}".format(path)
    with open(path) as f:
        return {"public/code-review/coverity.json": json.load(f)}


def test_simple(mock_revision, mock_config, log, mock_hgmo):
    """
    Test parsing a simple Coverity artifact
    """

    task = MockCoverityTask()
    issues = task.parse_issues(mock_coverity("simple"), mock_revision)
    assert len(issues) == 1
    assert all(map(lambda i: isinstance(i, CoverityIssue), issues))

    issue = issues[0]

    assert issue.analyzer == "mock-coverity"
    assert issue.revision == mock_revision
    assert issue.reliability == Reliability.Medium
    assert issue.path == "js/src/jit/BaselineCompiler.cpp"
    assert issue.line == 3703
    assert issue.check == "NULL_RETURNS"
    assert (
        issue.message
        == """Dereferencing a pointer that might be "nullptr" "env" when calling "lookupImport".
The path that leads to this defect is:

- ///builds/worker/checkouts/gecko/js/src/jit/BaselineCompiler.cpp:3697//:
-- `returned_null: "GetModuleEnvironmentForScript" returns "nullptr" (checked 2 out of 2 times).`.

- ///builds/worker/checkouts/gecko/js/src/jit/BaselineCompiler.cpp:3697//:
-- `var_assigned: Assigning: "env" = "nullptr" return value from "GetModuleEnvironmentForScript".`.

- ///builds/worker/checkouts/gecko/js/src/jit/BaselineCompiler.cpp:3703//:
-- `dereference: Dereferencing a pointer that might be "nullptr" "env" when calling "lookupImport".`.
"""
    )
    assert issue.state_on_server == {
        "cached": False,
        "cid": 95687,
        "components": ["js"],
        "customTriage": {},
        "firstDetectedDateTime": "2019-04-08T12:57:07+00:00",
        "ownerLdapServerName": "local",
        "presentInReferenceSnapshot": False,
        "retrievalDateTime": "2019-05-13T10:20:22+00:00",
        "stream": "Firefox",
        "triage": {
            "action": "Undecided",
            "classification": "Unclassified",
            "externalReference": "",
            "fixTarget": "Untargeted",
            "legacy": "False",
            "owner": "try",
            "severity": "Unspecified",
        },
    }
    assert issue.nb_lines == 1

    # Check the issue's absolute path has been cleaned
    assert log.has(
        "Cleaned issue absolute path",
        path="/builds/worker/checkouts/gecko/js/src/jit/BaselineCompiler.cpp",
        name="mock-coverity",
        level="warning",
    )

    assert issue.validates()
    assert not issue.is_publishable()

    checker_desc = """Checker reliability is medium, meaning that the false positive ratio is medium.
Dereferencing a pointer that might be "nullptr" "env" when calling "lookupImport".
The path that leads to this defect is:

- ///builds/worker/checkouts/gecko/js/src/jit/BaselineCompiler.cpp:3697//:
-- `returned_null: "GetModuleEnvironmentForScript" returns "nullptr" (checked 2 out of 2 times).`.

- ///builds/worker/checkouts/gecko/js/src/jit/BaselineCompiler.cpp:3697//:
-- `var_assigned: Assigning: "env" = "nullptr" return value from "GetModuleEnvironmentForScript".`.

- ///builds/worker/checkouts/gecko/js/src/jit/BaselineCompiler.cpp:3703//:
-- `dereference: Dereferencing a pointer that might be "nullptr" "env" when calling "lookupImport".`.
"""
    assert issue.as_phabricator_lint() == {
        "code": "coverity.NULL_RETURNS",
        "line": 3703,
        "name": checker_desc,
        "path": "js/src/jit/BaselineCompiler.cpp",
        "severity": "error",
    }

    assert issue.as_text() == checker_desc
    assert issue.as_dict() == {
        "analyzer": "mock-coverity",
        "in_patch": False,
        "is_new": False,
        "check": "NULL_RETURNS",
        "column": None,
        "level": "error",
        "line": 3703,
        "message": """Dereferencing a pointer that might be "nullptr" "env" when calling "lookupImport".
The path that leads to this defect is:

- ///builds/worker/checkouts/gecko/js/src/jit/BaselineCompiler.cpp:3697//:
-- `returned_null: "GetModuleEnvironmentForScript" returns "nullptr" (checked 2 out of 2 times).`.

- ///builds/worker/checkouts/gecko/js/src/jit/BaselineCompiler.cpp:3697//:
-- `var_assigned: Assigning: "env" = "nullptr" return value from "GetModuleEnvironmentForScript".`.

- ///builds/worker/checkouts/gecko/js/src/jit/BaselineCompiler.cpp:3703//:
-- `dereference: Dereferencing a pointer that might be "nullptr" "env" when calling "lookupImport".`.
""",
        "nb_lines": 1,
        "path": "js/src/jit/BaselineCompiler.cpp",
        "publishable": False,
        "validates": True,
        "hash": "4304590c14cd2ed9e7a7f913165af94b",
    }
