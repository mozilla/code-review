# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest
import responses
from libmozdata.phabricator import BuildState

from code_review_bot import Level
from code_review_bot import stats


def check_stats(summary_check):
    """
    Helper to check stat metrics after a workflow has run
    """
    assert len(stats.metrics) == len(summary_check)
    assert all(
        m["tags"]["app"] == "code-review-bot" and m["tags"]["channel"] == "test"
        for m in stats.metrics
    )
    assert all(m["measurement"].startswith("code-review.") for m in stats.metrics)
    stats_summary = [
        (
            m["measurement"],
            m["tags"].get("task"),
            m["fields"]["value"] if "runtime" not in m["measurement"] else "runtime",
        )
        for m in stats.metrics
    ]
    assert stats_summary == summary_check

    return True


def test_no_deps(mock_config, mock_revision, mock_workflow, mock_backend):
    """
    Test an error occurs when no dependencies are found on root task
    """
    mock_workflow.setup_mock_tasks(
        {
            "decision": {
                "image": "taskcluster/decision:XXX",
                "env": {
                    "GECKO_HEAD_REPOSITORY": "https://hg.mozilla.org/try",
                    "GECKO_HEAD_REV": "deadbeef1234",
                },
            },
            "remoteTryTask": {},
            "extra-task": {},
        }
    )

    with pytest.raises(AssertionError) as e:
        mock_workflow.run(mock_revision)
    assert str(e.value) == "No task dependencies to analyze"


def test_baseline(mock_config, mock_revision, mock_workflow, mock_backend, mock_hgmo):
    """
    Test a normal remote workflow (aka Try mode)
    - current task with analyzer deps
    - an analyzer in failed status
    - with some issues in its log
    """
    from code_review_bot.tasks.coverage import CoverageIssue
    from code_review_bot.tasks.lint import MozLintIssue

    # We run on a mock TC, with a try source
    if mock_config.taskcluster.local:
        assert mock_config.taskcluster.task_id == "local instance"
        assert mock_config.try_task_id == "remoteTryTask"

    mock_workflow.setup_mock_tasks(
        {
            "decision": {
                "image": "taskcluster/decision:XXX",
                "env": {
                    "GECKO_HEAD_REPOSITORY": "https://hg.mozilla.org/try",
                    "GECKO_HEAD_REV": "deadbeef1234",
                },
            },
            "remoteTryTask": {"dependencies": ["analyzer-A", "analyzer-B"]},
            "analyzer-A": {
                "name": "source-test-mozlint-flake8",
                "state": "failed",
                "artifacts": {
                    "public/code-review/mozlint.json": {
                        "test.cpp": [
                            {
                                "path": "test.cpp",
                                "lineno": 12,
                                "column": 1,
                                "level": "error",
                                "linter": "flake8",
                                "rule": "checker XXX",
                                "message": "strange issue",
                            }
                        ]
                    }
                },
            },
            "analyzer-B": {},
            "extra-task": {},
            "zero-cov": {
                "route": "project.relman.code-coverage.production.cron.latest",
                "artifacts": {
                    "public/zero_coverage_report.json": {
                        "files": [{"uncovered": True, "name": "test.cpp"}]
                    }
                },
            },
        }
    )
    issues = mock_workflow.run(mock_revision)

    assert len(issues) == 2
    issue = issues[0]
    assert isinstance(issue, MozLintIssue)
    assert issue.path == "test.cpp"
    assert issue.line == 12
    assert issue.column == 1
    assert issue.message == "strange issue"
    assert issue.check == "checker XXX"
    assert issue.revision is mock_revision
    assert issue.validates()

    issue = issues[1]
    assert isinstance(issue, CoverageIssue)
    assert issue.path == "test.cpp"
    assert issue.message == "This file is uncovered"
    assert issue.line is None
    assert issue.validates()

    assert check_stats(
        [
            ("code-review.analysis.files", None, 2),
            ("code-review.analysis.lines", None, 2),
            ("code-review.issues", "source-test-mozlint-flake8", 1),
            ("code-review.issues.publishable", "source-test-mozlint-flake8", 1),
            ("code-review.issues.paths", "source-test-mozlint-flake8", 1),
            ("code-review.issues", "source-test-mozlint-zero-cov", 1),
            ("code-review.issues.publishable", "source-test-mozlint-zero-cov", 1),
            ("code-review.issues.paths", "source-test-mozlint-zero-cov", 1),
            ("code-review.analysis.issues.publishable", None, 2),
            ("code-review.runtime.reports", None, "runtime"),
        ]
    )


def test_no_failed(mock_config, mock_revision, mock_workflow, mock_backend):
    """
    Test a remote workflow without any failed tasks
    """

    mock_workflow.setup_mock_tasks(
        {
            "decision": {
                "image": "taskcluster/decision:XXX",
                "env": {
                    "GECKO_HEAD_REPOSITORY": "https://hg.mozilla.org/try",
                    "GECKO_HEAD_REV": "deadbeef1234",
                },
            },
            "remoteTryTask": {"dependencies": ["analyzer-A", "analyzer-B"]},
            "analyzer-A": {},
            "analyzer-B": {},
            "extra-task": {},
        }
    )
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 0


def test_no_issues(mock_config, mock_revision, mock_workflow, mock_backend):
    """
    Test a remote workflow without any issues in its artifacts
    """

    mock_workflow.setup_mock_tasks(
        {
            "decision": {
                "image": "taskcluster/decision:XXX",
                "env": {
                    "GECKO_HEAD_REPOSITORY": "https://hg.mozilla.org/try",
                    "GECKO_HEAD_REV": "deadbeef1234",
                },
            },
            "remoteTryTask": {"dependencies": ["analyzer-A", "analyzer-B"]},
            "analyzer-A": {},
            "analyzer-B": {
                "name": "source-test-mozlint-flake8",
                "state": "failed",
                "artifacts": {
                    "nope.log": "No issues here !",
                    "still-nope.txt": "xxxxx",
                    "public/code-review/mozlint.json": {},
                },
            },
            "extra-task": {},
        }
    )
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 0
    assert mock_revision._state == BuildState.Fail

    # Now mark that task failure as ignorable
    mock_workflow.task_failures_ignored = ["source-test-mozlint-flake8"]
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 0
    assert mock_revision._state == BuildState.Pass


def test_unsupported_analyzer(mock_config, mock_revision, mock_workflow, mock_backend):
    """
    Test a remote workflow with an unsupported analyzer (not mozlint)
    """

    mock_workflow.setup_mock_tasks(
        {
            "decision": {
                "image": "taskcluster/decision:XXX",
                "env": {
                    "GECKO_HEAD_REPOSITORY": "https://hg.mozilla.org/try",
                    "GECKO_HEAD_REV": "deadbeef1234",
                },
            },
            "remoteTryTask": {"dependencies": ["analyzer-A", "analyzer-B"]},
            "analyzer-A": {},
            "analyzer-B": {
                "name": "custom-analyzer-from-vendor",
                "state": "failed",
                "artifacts": {
                    "issue.log": "TEST-UNEXPECTED-ERROR | test.cpp:12:1 | clearly an issue (checker XXX)"
                },
            },
            "extra-task": {},
        }
    )
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 0


def test_decision_task(mock_config, mock_revision, mock_workflow, mock_backend):
    """
    Test a remote workflow with different decision task setup
    """
    # Reset mercurial revision to enable setup_try to run
    mock_revision.mercurial_revision = None

    assert mock_revision.phabricator_repository["fields"]["name"] == "mozilla-central"

    mock_workflow.setup_mock_tasks({"notDecision": {}, "remoteTryTask": {}})
    with pytest.raises(Exception) as e:
        mock_workflow.run(mock_revision)
    assert str(e.value) == "Missing decision task"

    mock_workflow.setup_mock_tasks({"decision": {}, "remoteTryTask": {}})
    with pytest.raises(AssertionError) as e:
        mock_revision.phabricator_repository["fields"]["name"] = "unknown"
        mock_workflow.run(mock_revision)
    assert str(e.value) == "Unsupported decision task"

    # Restore name
    mock_revision.phabricator_repository["fields"]["name"] = "mozilla-central"
    mock_workflow.setup_mock_tasks({"decision": {}, "remoteTryTask": {}})
    with pytest.raises(Exception) as e:
        mock_workflow.run(mock_revision)
    assert str(e.value) == "Revision GECKO_HEAD_REV not found in decision task"

    mock_workflow.setup_mock_tasks(
        {"decision": {"image": "anotherImage"}, "remoteTryTask": {}}
    )
    with pytest.raises(Exception) as e:
        mock_workflow.run(mock_revision)
    assert str(e.value) == "Revision GECKO_HEAD_REV not found in decision task"

    mock_workflow.setup_mock_tasks(
        {
            "decision": {
                "image": {"from": "taskcluster/decision", "tag": "unsupported"}
            },
            "remoteTryTask": {},
        }
    )
    with pytest.raises(Exception) as e:
        mock_workflow.run(mock_revision)
    assert str(e.value) == "Revision GECKO_HEAD_REV not found in decision task"

    mock_workflow.setup_mock_tasks(
        {"decision": {"image": "taskcluster/decision:XXX"}, "remoteTryTask": {}}
    )
    with pytest.raises(Exception) as e:
        mock_workflow.run(mock_revision)
    assert str(e.value) == "Revision GECKO_HEAD_REV not found in decision task"

    mock_workflow.setup_mock_tasks(
        {
            "decision": {
                "image": "taskcluster/decision:XXX",
                "env": {"GECKO_HEAD_REV": "someRevision"},
            },
            "remoteTryTask": {},
        }
    )
    with pytest.raises(Exception) as e:
        mock_workflow.run(mock_revision)
    assert str(e.value) == "Repository GECKO_HEAD_REPOSITORY not found in decision task"
    assert mock_revision.mercurial_revision is None

    mock_workflow.setup_mock_tasks(
        {
            "decision": {
                "image": "taskcluster/decision:XXX",
                "env": {
                    "GECKO_HEAD_REV": "someRevision",
                    "GECKO_HEAD_REPOSITORY": "https://hg.mozilla.org/try",
                },
            },
            "remoteTryTask": {},
        }
    )
    with pytest.raises(AssertionError) as e:
        mock_workflow.run(mock_revision)
    assert str(e.value) == "No task dependencies to analyze"
    assert mock_revision.mercurial_revision is not None
    assert mock_revision.mercurial_revision == "someRevision"


def test_mozlint_task(mock_config, mock_revision, mock_workflow, mock_backend):
    """
    Test a remote workflow with a mozlint analyzer
    """
    from code_review_bot.tasks.lint import MozLintIssue

    mock_workflow.setup_mock_tasks(
        {
            "decision": {
                "image": "taskcluster/decision:XXX",
                "env": {
                    "GECKO_HEAD_REPOSITORY": "https://hg.mozilla.org/try",
                    "GECKO_HEAD_REV": "deadbeef1234",
                },
            },
            "remoteTryTask": {"dependencies": ["mozlint"]},
            "mozlint": {
                "name": "source-test-mozlint-dummy",
                "state": "failed",
                "artifacts": {
                    "public/code-review/mozlint.json": {
                        "test.cpp": [
                            {
                                "path": "test.cpp",
                                "lineno": 42,
                                "column": 51,
                                "level": "error",
                                "linter": "flake8",
                                "rule": "E001",
                                "message": "dummy issue",
                            }
                        ]
                    }
                },
            },
        }
    )
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, MozLintIssue)
    assert issue.path == "test.cpp"
    assert issue.line == 42
    assert issue.column == 51
    assert issue.linter == "flake8"
    assert issue.message == "dummy issue"

    assert check_stats(
        [
            ("code-review.analysis.files", None, 2),
            ("code-review.analysis.lines", None, 2),
            ("code-review.issues", "source-test-mozlint-dummy", 1),
            ("code-review.issues.publishable", "source-test-mozlint-dummy", 1),
            ("code-review.issues.paths", "source-test-mozlint-dummy", 1),
            ("code-review.analysis.issues.publishable", None, 1),
            ("code-review.runtime.reports", None, "runtime"),
        ]
    )


def test_clang_tidy_task(mock_config, mock_revision, mock_workflow, mock_backend):
    """
    Test a remote workflow with a clang-tidy analyzer
    """
    from code_review_bot import Reliability
    from code_review_bot.tasks.clang_tidy import ClangTidyIssue

    mock_workflow.setup_mock_tasks(
        {
            "decision": {
                "image": "taskcluster/decision:XXX",
                "env": {
                    "GECKO_HEAD_REPOSITORY": "https://hg.mozilla.org/try",
                    "GECKO_HEAD_REV": "deadbeef1234",
                },
            },
            "remoteTryTask": {"dependencies": ["clang-tidy"]},
            "clang-tidy": {
                "name": "source-test-clang-tidy",
                "state": "completed",
                "artifacts": {
                    "public/code-review/clang-tidy.json": {
                        "files": {
                            "test.cpp": {
                                "hash": "e409f05a10574adb8d47dcb631f8e3bb",
                                "warnings": [
                                    {
                                        "column": 12,
                                        "line": 123,
                                        "flag": "checker.XXX",
                                        "reliability": "high",
                                        "message": "some hard issue with c++",
                                        "filename": "test.cpp",
                                    },
                                    {
                                        "column": 51,
                                        "line": 987,
                                        "type": "error",
                                        "flag": "clang-diagnostic-error",
                                        # No reliability !
                                        "message": "some harder issue with c++",
                                        "filename": "test.cpp",
                                    },
                                ],
                            }
                        }
                    }
                },
            },
        }
    )
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 2
    issue = issues[0]
    assert isinstance(issue, ClangTidyIssue)
    assert issue.path == "test.cpp"
    assert issue.line == 123
    assert issue.column == 12
    assert issue.check == "checker.XXX"
    assert issue.reliability == Reliability.High
    assert issue.message == "some hard issue with c++"
    assert not issue.is_build_error()

    issue = issues[1]
    assert isinstance(issue, ClangTidyIssue)
    assert issue.path == "test.cpp"
    assert issue.line == 987
    assert issue.column == 51
    assert issue.check == "clang-diagnostic-error"
    assert issue.reliability == Reliability.Unknown
    assert issue.message == "some harder issue with c++"
    assert issue.is_build_error()
    assert check_stats(
        [
            ("code-review.analysis.files", None, 2),
            ("code-review.analysis.lines", None, 2),
            ("code-review.issues", "source-test-clang-tidy", 2),
            ("code-review.issues.publishable", "source-test-clang-tidy", 0),
            ("code-review.issues.paths", "source-test-clang-tidy", 1),
            ("code-review.analysis.issues.publishable", None, 0),
            ("code-review.runtime.reports", None, "runtime"),
        ]
    )


CLANG_FORMAT_PATCH = """
--- test.cpp	13:19:38.060336000 +0000
+++ test.cpp	13:22:36.680336000 +0000
@@ -1384,4 +1384,4@@
 some line
 another line
-remove
-remove
+Multi
+lines

"""


def test_clang_format_task(
    mock_config, mock_revision, mock_workflow, mock_hgmo, mock_backend
):
    """
    Test a remote workflow with a clang-format analyzer
    """
    from code_review_bot.tasks.clang_format import ClangFormatIssue

    # Mock for artifact upload
    responses.add(
        responses.PUT,
        "http://storage.test/public/patch/clang-format-PHID-DIFF-test.diff",
        json={},
        headers={"ETag": "test123"},
    )

    tasks = {
        "decision": {
            "image": "taskcluster/decision:XXX",
            "env": {
                "GECKO_HEAD_REPOSITORY": "https://hg.mozilla.org/try",
                "GECKO_HEAD_REV": "deadbeef1234",
            },
        },
        "remoteTryTask": {"dependencies": ["clang-format"]},
        "clang-format": {
            "name": "source-test-clang-format",
            "state": "completed",
            "artifacts": {"public/code-review/clang-format.diff": CLANG_FORMAT_PATCH},
        },
    }
    mock_workflow.setup_mock_tasks(tasks)
    assert len(mock_revision.improvement_patches) == 0
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, ClangFormatIssue)
    assert issue.path == "test.cpp"
    assert issue.line == 1386
    assert issue.nb_lines == 2
    assert issue.fix == "Multi\nlines"
    assert issue.language == "c++"
    assert issue.column is None
    assert issue.as_dict() == {
        "analyzer": "source-test-clang-format",
        "check": "invalid-styling",
        "level": "warning",
        "message": "The change does not follow the C/C++ coding style, please reformat",
        "column": None,
        "in_patch": False,
        "line": 1386,
        "nb_lines": 2,
        "path": "test.cpp",
        "publishable": False,
        "validates": False,
        "hash": "56f81d5190f8e1bd7a7d2380e7da6d67",
        "fix": "Multi\nlines",
    }
    assert issue.as_phabricator_lint() == {
        "code": "invalid-styling",
        "description": """WARNING: The change does not follow the C/C++ coding style, please reformat

  lang=c++
  Multi
  lines""",
        "line": 1386,
        "name": "clang-format",
        "path": "test.cpp",
        "severity": "warning",
    }
    assert len(mock_revision.improvement_patches) == 1

    assert check_stats(
        [
            ("code-review.analysis.files", None, 2),
            ("code-review.analysis.lines", None, 2),
            ("code-review.issues", "source-test-clang-format", 1),
            ("code-review.issues.publishable", "source-test-clang-format", 0),
            ("code-review.issues.paths", "source-test-clang-format", 1),
            ("code-review.analysis.issues.publishable", None, 0),
            ("code-review.runtime.reports", None, "runtime"),
        ]
    )


def test_coverity_task(
    mock_config, mock_revision, mock_workflow, mock_backend, mock_hgmo
):
    """
    Test a remote workflow with a clang-tidy analyzer
    """
    from code_review_bot import Reliability
    from code_review_bot.tasks.coverity import CoverityIssue

    mock_workflow.setup_mock_tasks(
        {
            "decision": {
                "image": "taskcluster/decision:XXX",
                "env": {
                    "GECKO_HEAD_REPOSITORY": "https://hg.mozilla.org/try",
                    "GECKO_HEAD_REV": "deadbeef1234",
                },
            },
            "remoteTryTask": {"dependencies": ["coverity"]},
            "coverity": {
                "name": "source-test-coverity-coverity",
                "state": "completed",
                "artifacts": {
                    "public/code-review/coverity.json": {
                        "files": {
                            "test.cpp": {
                                "warnings": [
                                    {
                                        "line": 66,
                                        "flag": "UNINIT",
                                        "reliability": "high",
                                        "message": 'Using uninitialized value "a".',
                                        "extra": {
                                            "category": "Memory - corruptions",
                                            "stateOnServer": {
                                                "presentInReferenceSnapshot": False
                                            },
                                            "stack": [
                                                {
                                                    "line_number": 61,
                                                    "description": 'Condition "!target.oper…", taking false branch.',
                                                    "file_path": "dom/animation/Animation.cpp",
                                                    "path_type": "path",
                                                }
                                            ],
                                        },
                                    }
                                ]
                            }
                        }
                    }
                },
            },
        }
    )
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, CoverityIssue)
    assert issue.path == "test.cpp"
    assert issue.line == 66
    assert issue.check == "UNINIT"
    assert issue.reliability == Reliability.High
    assert (
        issue.message
        == """Using uninitialized value "a".
The path that leads to this defect is:

- //dom/animation/Animation.cpp:61//:
-- `path: Condition \"!target.oper…", taking false branch.`.\n"""
    )
    assert issue.is_local()
    assert issue.validates()

    assert check_stats(
        [
            ("code-review.analysis.files", None, 2),
            ("code-review.analysis.lines", None, 2),
            ("code-review.issues", "source-test-coverity-coverity", 1),
            ("code-review.issues.publishable", "source-test-coverity-coverity", 0),
            ("code-review.issues.paths", "source-test-coverity-coverity", 1),
            ("code-review.analysis.issues.publishable", None, 0),
            ("code-review.runtime.reports", None, "runtime"),
        ]
    )


def test_infer_task(mock_config, mock_revision, mock_workflow, mock_hgmo, mock_backend):
    """
    Test a remote workflow with an infer analyzer
    """
    from code_review_bot.tasks.infer import InferIssue

    mock_workflow.setup_mock_tasks(
        {
            "decision": {
                "image": "taskcluster/decision:XXX",
                "env": {
                    "GECKO_HEAD_REPOSITORY": "https://hg.mozilla.org/try",
                    "GECKO_HEAD_REV": "deadbeef1234",
                },
            },
            "remoteTryTask": {"dependencies": ["infer"]},
            "infer": {
                "name": "source-test-infer-infer",
                "state": "completed",
                "artifacts": {
                    "public/code-review/infer.json": [
                        {
                            "bug_class": "PROVER",
                            "kind": "error",
                            "bug_type": "THREAD_SAFETY_VIOLATION",
                            "qualifier": "Read/Write race.",
                            "severity": "HIGH",
                            "visibility": "user",
                            "line": 1196,
                            "column": -1,
                            "procedure": "void Bad.Function(Test,int)",
                            "procedure_id": "org.mozilla.geckoview.somewhere(, mock_workflow):void",
                            "procedure_start_line": 0,
                            "file": "mobile/android/geckoview/src/main/java/org/mozilla/test.java",
                            "bug_trace": [
                                {
                                    "level": 0,
                                    "filename": "mobile/android/geckoview/src/main/java/org/mozilla/test.java",
                                    "line_number": 1196,
                                    "column_number": -1,
                                    "description": "<Read trace>",
                                }
                            ],
                            "key": "GeckoSession.java|test|THREAD_SAFETY_VIOLATION",
                            "node_key": "9c5d6d9028928346cc4fb44cced5dea1",
                            "hash": "b008b0dd2b74e6036fa2105f7e54458e",
                            "bug_type_hum": "Thread Safety Violation",
                            "censored_reason": "",
                            "access": "reallyLongHash",
                        }
                    ]
                },
            },
        }
    )
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, InferIssue)
    assert issue.path == "mobile/android/geckoview/src/main/java/org/mozilla/test.java"
    assert issue.line == 1196
    assert issue.column == -1
    assert issue.check == "THREAD_SAFETY_VIOLATION"
    assert issue.level == Level.Warning
    assert issue.message == "Read/Write race."
    assert issue.nb_lines == 1
    assert issue.as_dict() == {
        "analyzer": "source-test-infer-infer",
        "check": "THREAD_SAFETY_VIOLATION",
        "column": -1,
        "in_patch": False,
        "level": "warning",
        "line": 1196,
        "message": "Read/Write race.",
        "nb_lines": 1,
        "path": "mobile/android/geckoview/src/main/java/org/mozilla/test.java",
        "publishable": False,
        "validates": True,
        "hash": "02353719655edb9ba07e0bd0cacd620b",
        "fix": None,
    }


def test_no_tasks(mock_config, mock_revision, mock_workflow, mock_backend):
    """
    Test a remote workflow with only a Gecko decision task as dep
    https://github.com/mozilla/release-services/issues/2055
    """

    mock_workflow.setup_mock_tasks(
        {
            "decision": {
                "image": "taskcluster/decision:XXX",
                "env": {
                    "GECKO_HEAD_REPOSITORY": "https://hg.mozilla.org/try",
                    "GECKO_HEAD_REV": "deadbeef1234",
                },
                "name": "Gecko Decision Task",
            },
            "remoteTryTask": {"dependencies": ["decision", "someOtherDockerbuild"]},
        }
    )
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 0


def test_zero_coverage_option(mock_config, mock_revision, mock_workflow, mock_backend):
    """
    Test the zero coverage trigger on the workflow
    """
    from code_review_bot.tasks.coverage import CoverageIssue

    mock_workflow.setup_mock_tasks(
        {
            "decision": {
                "image": "taskcluster/decision:XXX",
                "env": {
                    "GECKO_HEAD_REPOSITORY": "https://hg.mozilla.org/try",
                    "GECKO_HEAD_REV": "deadbeef1234",
                },
            },
            "remoteTryTask": {"dependencies": ["xxx"]},
            "zero-cov": {
                "route": "project.relman.code-coverage.production.cron.latest",
                "artifacts": {
                    "public/zero_coverage_report.json": {
                        "files": [{"uncovered": True, "name": "test.cpp"}]
                    }
                },
            },
        }
    )

    mock_workflow.zero_coverage_enabled = False
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 0

    mock_workflow.zero_coverage_enabled = True
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 1
    assert isinstance(issues[0], CoverageIssue)
