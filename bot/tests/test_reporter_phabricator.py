# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
import unittest
from unittest.mock import MagicMock

import pytest
import responses
from requests.exceptions import HTTPError
from structlog.testing import capture_logs

from code_review_bot import Level
from code_review_bot.report.phabricator import PhabricatorReporter
from code_review_bot.revisions import ImprovementPatch, Revision
from code_review_bot.tasks.clang_format import ClangFormatIssue, ClangFormatTask
from code_review_bot.tasks.clang_tidy import ClangTidyIssue, ClangTidyTask
from code_review_bot.tasks.clang_tidy_external import (
    ExternalTidyIssue,
    ExternalTidyTask,
)
from code_review_bot.tasks.coverage import CoverageIssue, ZeroCoverageTask
from code_review_bot.tasks.default import DefaultIssue, DefaultTask
from code_review_bot.tasks.docupload import COMMENT_LINK_TO_DOC
from code_review_bot.tasks.lint import MozLintIssue, MozLintTask
from code_review_bot.tasks.tgdiff import COMMENT_TASKGRAPH_DIFF

VALID_CLANG_TIDY_MESSAGE = """
Code analysis found 1 defect in diff [42](https://phabricator.services.mozilla.com/differential/diff/42/):
 - 1 defect found by clang-tidy

WARNING: Found 1 defect (warning level) that can be dismissed.

You can run this analysis locally with:
 - `./mach static-analysis check --outgoing` (C/C++)


---

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Developer+Infrastructure&component=Source+Code+Analysis&short_desc=[Automated+review]+THIS+IS+A+PLACEHOLDER&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).

You can view these defects in the Diff Detail section of [Phabricator diff 42](https://phabricator.services.mozilla.com/differential/diff/42/).
"""

VALID_BUILD_ERROR_MESSAGE = """
Code analysis found 1 defect in diff [42](https://phabricator.services.mozilla.com/differential/diff/42/):
 - 1 build error found by clang-tidy

IMPORTANT: Found 1 defect (error level) that must be fixed before landing.

You can run this analysis locally with:
 - `./mach static-analysis check --outgoing` (C/C++)


---

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Developer+Infrastructure&component=Source+Code+Analysis&short_desc=[Automated+review]+THIS+IS+A+PLACEHOLDER&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).

You can view these defects in the Diff Detail section of [Phabricator diff 42](https://phabricator.services.mozilla.com/differential/diff/42/).
"""

VALID_CLANG_FORMAT_MESSAGE = """
Code analysis found 1 defect in diff [42](https://phabricator.services.mozilla.com/differential/diff/42/):
 - 1 defect found by clang-format

WARNING: Found 1 defect (warning level) that can be dismissed.

You can run this analysis locally with:
 - `./mach clang-format -p dom/test.cpp`

For your convenience, [here is a patch]({results}/source-test-clang-format-PHID-DIFF-test.diff) that fixes all the clang-format defects (use it in your repository with `hg import` or `git apply -p0`).


---

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Developer+Infrastructure&component=Source+Code+Analysis&short_desc=[Automated+review]+THIS+IS+A+PLACEHOLDER&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).

You can view these defects in the Diff Detail section of [Phabricator diff 42](https://phabricator.services.mozilla.com/differential/diff/42/).
"""

VALID_FLAKE8_MESSAGE = """
Code analysis found 2 defects in diff [42](https://phabricator.services.mozilla.com/differential/diff/42/):
 - 1 defect found by eslint (Mozlint)
 - 1 defect found by py-flake8 (Mozlint)

WARNING: Found 1 defect (warning level) that can be dismissed.

IMPORTANT: Found 1 defect (error level) that must be fixed before landing.

You can run this analysis locally with:
 - `./mach lint --warnings --outgoing`


---

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Developer+Infrastructure&component=Source+Code+Analysis&short_desc=[Automated+review]+THIS+IS+A+PLACEHOLDER&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).

You can view these defects in the Diff Detail section of [Phabricator diff 42](https://phabricator.services.mozilla.com/differential/diff/42/).
"""

VALID_COVERAGE_MESSAGE = """
Code analysis found 1 defect in diff [42](https://phabricator.services.mozilla.com/differential/diff/42/):
 - 1 defect found by code coverage analysis

WARNING: Found 1 defect (warning level) that can be dismissed.

In our previous code coverage analysis run, we found some files which had no coverage and are being modified in this patch:
Should they have tests, or are they dead code?

 - You can file a bug blocking [Bug 1415824](https://bugzilla.mozilla.org/show_bug.cgi?id=1415824) for untested files that should be **tested**.
 - You can file a bug blocking [Bug 1415819](https://bugzilla.mozilla.org/show_bug.cgi?id=1415819) for untested files that should be **removed**.


---

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Developer+Infrastructure&component=Source+Code+Analysis&short_desc=[Automated+review]+THIS+IS+A+PLACEHOLDER&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).

You can view these defects in the Diff Detail section of [Phabricator diff 42](https://phabricator.services.mozilla.com/differential/diff/42/).
"""

VALID_DEFAULT_MESSAGE = """
Code analysis found 1 defect in diff [42](https://phabricator.services.mozilla.com/differential/diff/42/):
 - 1 defect found by full-file-analyzer

WARNING: Found 1 defect (warning level) that can be dismissed.


---

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Developer+Infrastructure&component=Source+Code+Analysis&short_desc=[Automated+review]+THIS+IS+A+PLACEHOLDER&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).

You can view these defects in the Diff Detail section of [Phabricator diff 42](https://phabricator.services.mozilla.com/differential/diff/42/).
"""

VALID_TASK_FAILURES_MESSAGE = """
The analysis task [mock-clang-tidy](https://treeherder.mozilla.org/#/jobs?repo=try&revision=deadc0ffee&selectedTaskRun=ab3NrysvSZyEwsOHL2MZfw-0) failed, but we could not detect any defect.
Please check this task manually.


---

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Developer+Infrastructure&component=Source+Code+Analysis&short_desc=[Automated+review]+THIS+IS+A+PLACEHOLDER&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).
"""

VALID_MOZLINT_MESSAGE = """
Code analysis found 2 defects in diff [42](https://phabricator.services.mozilla.com/differential/diff/42/):
 - 2 defects found by dummy (Mozlint)

WARNING: Found 1 defect (warning level) that can be dismissed.

IMPORTANT: Found 1 defect (error level) that must be fixed before landing.

You can run this analysis locally with:
 - `./mach lint --warnings --outgoing`


---

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Developer+Infrastructure&component=Source+Code+Analysis&short_desc=[Automated+review]+THIS+IS+A+PLACEHOLDER&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).

You can view these defects in the Diff Detail section of [Phabricator diff 42](https://phabricator.services.mozilla.com/differential/diff/42/).
"""

VALID_CLANG_TIDY_COVERAGE_MESSAGE = """
Code analysis found 2 defects in diff [42](https://phabricator.services.mozilla.com/differential/diff/42/):
 - 1 defect found by clang-tidy
 - 1 defect found by code coverage analysis

WARNING: Found 2 defects (warning level) that can be dismissed.

You can run this analysis locally with:
 - `./mach static-analysis check --outgoing` (C/C++)

In our previous code coverage analysis run, we found some files which had no coverage and are being modified in this patch:
Should they have tests, or are they dead code?

 - You can file a bug blocking [Bug 1415824](https://bugzilla.mozilla.org/show_bug.cgi?id=1415824) for untested files that should be **tested**.
 - You can file a bug blocking [Bug 1415819](https://bugzilla.mozilla.org/show_bug.cgi?id=1415819) for untested files that should be **removed**.


---

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Developer+Infrastructure&component=Source+Code+Analysis&short_desc=[Automated+review]+THIS+IS+A+PLACEHOLDER&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).

You can view these defects in the Diff Detail section of [Phabricator diff 42](https://phabricator.services.mozilla.com/differential/diff/42/).
"""

VALID_NOTICE_MESSAGE = """
{notice}


---

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Developer+Infrastructure&component=Source+Code+Analysis&short_desc=[Automated+review]+THIS+IS+A+PLACEHOLDER&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).
"""

VALID_EXTERNAL_TIDY_MESSAGE = """
Code analysis found 1 defect in diff [42](https://phabricator.services.mozilla.com/differential/diff/42/):
 - 1 defect found by private static analysis

WARNING: Found 1 defect (warning level) that can be dismissed.

You can run this analysis locally with:
 - For private static analysis, please see [our private docs in Mana](https://mana.mozilla.org/wiki/pages/viewpage.action?pageId=130909687), if you cannot access this resource, ask your reviewer to help you resolve the issue.

#### Private Static Analysis warning

- **Message**: dummy message
- **Location**: another_test.cpp:43:9
- **Clang check**: mozilla-civet-private-checker-1
- **in an expanded Macro**: no



---

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Developer+Infrastructure&component=Source+Code+Analysis&short_desc=[Automated+review]+THIS+IS+A+PLACEHOLDER&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).

You can view these defects in the Diff Detail section of [Phabricator diff 42](https://phabricator.services.mozilla.com/differential/diff/42/).
"""

FOLLOW_UP_DIFF_MESSAGE = """
Code analysis found 2 defects in diff [42](https://phabricator.services.mozilla.com/differential/diff/42/):
 - 1 defect found by clang-format
 - 1 defect found by code coverage analysis
1 defect unresolved and 1 defect closed compared to the previous diff [41](https://phabricator.services.mozilla.com/differential/diff/41/).

WARNING: Found 2 defects (warning level) that can be dismissed.

You can run this analysis locally with:
 - `./mach clang-format -p dom/test.cpp`

In our previous code coverage analysis run, we found some files which had no coverage and are being modified in this patch:
Should they have tests, or are they dead code?

 - You can file a bug blocking [Bug 1415824](https://bugzilla.mozilla.org/show_bug.cgi?id=1415824) for untested files that should be **tested**.
 - You can file a bug blocking [Bug 1415819](https://bugzilla.mozilla.org/show_bug.cgi?id=1415819) for untested files that should be **removed**.


---

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Developer+Infrastructure&component=Source+Code+Analysis&short_desc=[Automated+review]+THIS+IS+A+PLACEHOLDER&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).\n
You can view these defects in the Diff Detail section of [Phabricator diff 42](https://phabricator.services.mozilla.com/differential/diff/42/).
"""

VALID_CLANG_BEFORE_AFTER_MESSAGE = """
Code analysis found 1 defect in diff [42](https://phabricator.services.mozilla.com/differential/diff/42/):
 - 1 defect found by clang-format

WARNING: Found 1 defect (warning level) that can be dismissed.

You can run this analysis locally with:
 - `./mach clang-format -p outside/of/the/patch.cpp`


---

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Developer+Infrastructure&component=Source+Code+Analysis&short_desc=[Automated+review]+THIS+IS+A+PLACEHOLDER&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).

You can view these defects in the Diff Detail section of [Phabricator diff 42](https://phabricator.services.mozilla.com/differential/diff/42/).
"""


def test_phabricator_clang_tidy(
    mock_phabricator, phab, mock_try_task, mock_decision_task, mock_task
):
    """
    Test Phabricator reporter publication on a mock clang-tidy issue
    """

    with mock_phabricator as api:
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)
        revision.lines = {
            # Add dummy lines diff
            "another_test.cpp": [41, 42, 43]
        }
        revision.files = ["another_test.cpp"]
        revision.id = 52
        reporter = PhabricatorReporter({"analyzers": ["clang-tidy"]}, api=api)

    issue = ClangTidyIssue(
        mock_task(ClangTidyTask, "source-test-clang-tidy"),
        revision,
        "another_test.cpp",
        "42",
        "51",
        "modernize-use-nullptr",
        "dummy message",
    )
    assert issue.is_publishable()

    issues, patches = reporter.publish([issue], revision, [], [], [])
    assert len(issues) == 1
    assert len(patches) == 0

    # Check the comment has been posted
    assert phab.comments[51] == [VALID_CLANG_TIDY_MESSAGE]


def test_phabricator_clang_format(
    mock_config, mock_phabricator, phab, mock_try_task, mock_decision_task, mock_task
):
    """
    Test Phabricator reporter publication on a mock clang-format issue
    """

    with mock_phabricator as api:
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)
        revision.lines = {
            # Add dummy lines diff
            "test.cpp": [41, 42, 43],
            "dom/test.cpp": [42],
        }
        revision.id = 52
        reporter = PhabricatorReporter({"analyzers": ["clang-format"]}, api=api)

    task = mock_task(ClangFormatTask, "source-test-clang-format")
    lines = [
        (41, 41, b"no change"),
        (42, None, b"deletion"),
        (None, 42, b"change here"),
    ]
    issue = ClangFormatIssue(task, "dom/test.cpp", lines, revision)
    assert issue.is_publishable()

    revision.improvement_patches = [
        ImprovementPatch(task, repr(revision), "Some lint fixes")
    ]
    list(map(lambda p: p.write(), revision.improvement_patches))  # trigger local write

    issues, patches = reporter.publish([issue], revision, [], [], [])
    assert len(issues) == 1
    assert len(patches) == 1

    # Check the comment has been posted
    assert phab.comments[51] == [
        VALID_CLANG_FORMAT_MESSAGE.format(results=mock_config.taskcluster.results_dir)
    ]


def test_phabricator_mozlint(
    mock_config, mock_phabricator, phab, mock_try_task, mock_decision_task, mock_task
):
    """
    Test Phabricator reporter publication on two mock mozlint issues
    using two different analyzers
    """

    with mock_phabricator as api:
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)
        revision.lines = {
            # Add dummy lines diff
            "python/test.py": [41, 42, 43],
            "js/test.js": [10, 11, 12],
            "dom/test.cpp": [42],
        }
        revision.files = revision.lines.keys()
        revision.id = 52
        reporter = PhabricatorReporter({}, api=api)

    issue_flake = MozLintIssue(
        analyzer=mock_task(MozLintTask, "source-test-mozlint-py-flake8"),
        path="python/test.py",
        lineno=42,
        column=1,
        message="A bad bad error",
        level="error",
        revision=revision,
        linter="flake8",
        check="EXXX",
    )
    assert issue_flake.is_publishable()

    issue_eslint = MozLintIssue(
        analyzer=mock_task(MozLintTask, "source-test-mozlint-eslint"),
        path="js/test.js",
        lineno=10,
        column=4,
        message="A bad error",
        level="warning",
        revision=revision,
        linter="eslint",
        check="YYY",
    )
    assert issue_eslint.is_publishable()

    issues, patches = reporter.publish(
        [issue_flake, issue_eslint], revision, [], [], []
    )
    assert len(issues) == 2
    assert len(patches) == 0

    # Check the callbacks have been used to publish either a lint result + summary comment
    assert phab.comments[51] == [
        VALID_FLAKE8_MESSAGE.format(results=mock_config.taskcluster.results_dir)
    ]
    assert phab.build_messages["PHID-HMBT-test"] == [
        {
            "receiver": "PHID-HMBT-test",
            "lint": [
                {
                    "char": 1,
                    "code": "EXXX",
                    "description": "(IMPORTANT) ERROR: A bad bad error",
                    "line": 42,
                    "name": "py-flake8 (Mozlint)",
                    "path": "python/test.py",
                    "severity": "error",
                },
                {
                    "char": 4,
                    "code": "YYY",
                    "description": "WARNING: A bad error",
                    "line": 10,
                    "name": "eslint (Mozlint)",
                    "path": "js/test.js",
                    "severity": "warning",
                },
            ],
            "unit": [],
            "type": "work",
        }
    ]


def test_phabricator_coverage(
    mock_config, mock_phabricator, phab, mock_try_task, mock_decision_task, mock_task
):
    """
    Test Phabricator reporter publication on a mock coverage issue
    """

    with mock_phabricator as api:
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)
        revision.lines = {
            # Add dummy lines diff
            "test.txt": [0],
            "path/to/test.cpp": [0],
            "dom/test.cpp": [42],
        }
        revision.id = 52
        reporter = PhabricatorReporter({"analyzers": ["coverage"]}, api=api)

    issue = CoverageIssue(
        mock_task(ZeroCoverageTask, "coverage"),
        "path/to/test.cpp",
        0,
        "This file is uncovered",
        revision,
    )
    assert issue.is_publishable()

    issues, patches = reporter.publish([issue], revision, [], [], [])
    assert len(issues) == 1
    assert len(patches) == 0

    # Check the lint results
    assert phab.build_messages["PHID-HMBT-test"] == [
        {
            "receiver": "PHID-HMBT-test",
            "lint": [
                {
                    "code": "no-coverage",
                    "description": "WARNING: This file is uncovered",
                    "line": 1,
                    "name": "code coverage analysis",
                    "path": "path/to/test.cpp",
                    "severity": "warning",
                }
            ],
            "type": "work",
            "unit": [],
        }
    ]

    # Check the callback has been used
    assert phab.comments[51] == [VALID_COVERAGE_MESSAGE]


def test_phabricator_no_coverage_on_deleted_file(
    monkeypatch,
    mock_config,
    mock_phabricator,
    phab,
    mock_try_task,
    mock_decision_task,
    mock_task,
):
    """
    Ensure missing coverage warning is not publicated when a file is deleted
    """

    def raise_404(*args, **kwargs):
        resp_mock = MagicMock()
        resp_mock.status_code = 404
        raise HTTPError(response=resp_mock)

    with mock_phabricator as api:
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)
        revision.lines = {
            # Add dummy lines diff
            "test.txt": [0],
            "path/to/test.cpp": [0],
            "dom/test.cpp": [42],
        }
        revision.id = 52
        monkeypatch.setattr(revision, "load_file", raise_404)

    issue = CoverageIssue(
        mock_task(ZeroCoverageTask, "coverage"),
        "path/to/test.cpp",
        0,
        "This file is uncovered",
        revision,
    )
    assert not issue.is_publishable()


def test_phabricator_clang_tidy_and_coverage(
    mock_config, mock_phabricator, phab, mock_try_task, mock_decision_task, mock_task
):
    """
    Test Phabricator reporter publication on a mock coverage issue
    """

    with mock_phabricator as api:
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)
        revision.lines = {
            # Add dummy lines diff
            "test.txt": [0],
            "path/to/test.cpp": [0],
            "another_test.cpp": [41, 42, 43],
        }
        revision.files = ["test.txt", "test.cpp", "another_test.cpp"]
        revision.id = 52
        reporter = PhabricatorReporter(
            {"analyzers": ["coverage", "clang-tidy"]}, api=api
        )

    issue_clang_tidy = ClangTidyIssue(
        mock_task(ClangTidyTask, "source-test-clang-tidy"),
        revision,
        "another_test.cpp",
        "42",
        "51",
        "modernize-use-nullptr",
        "dummy message",
    )
    assert issue_clang_tidy.is_publishable()

    issue_coverage = CoverageIssue(
        mock_task(ZeroCoverageTask, "coverage"),
        "path/to/test.cpp",
        0,
        "This file is uncovered",
        revision,
    )
    assert issue_coverage.is_publishable()

    issues, patches = reporter.publish(
        [issue_clang_tidy, issue_coverage], revision, [], [], []
    )
    assert len(issues) == 2
    assert len(patches) == 0

    # Check the lint results
    assert phab.build_messages["PHID-HMBT-test"] == [
        {
            "receiver": "PHID-HMBT-test",
            "lint": [
                {
                    "char": 51,
                    "code": "modernize-use-nullptr",
                    "description": "WARNING: dummy message",
                    "line": 42,
                    "name": "clang-tidy",
                    "path": "another_test.cpp",
                    "severity": "warning",
                },
                {
                    "code": "no-coverage",
                    "description": "WARNING: This file is uncovered",
                    "line": 1,
                    "name": "code coverage analysis",
                    "path": "path/to/test.cpp",
                    "severity": "warning",
                },
            ],
            "type": "work",
            "unit": [],
        }
    ]

    # Check the callback has been used to post unique comment
    assert phab.comments[51] == [VALID_CLANG_TIDY_COVERAGE_MESSAGE]


@pytest.mark.parametrize(
    "analyzers_skipped, valid_issues, valid_patches",
    [
        # All analyzers
        (
            [],
            [
                "mock-clang-format",
                "mock-clang-tidy",
                "mock-lint-flake8",
                "coverage",
            ],
            [
                "dummy",
                "mock-clang-tidy",
                "mock-clang-format",
                "mock-lint-flake8",
            ],
        ),
        # Skip clang-tidy
        (
            ["mock-clang-tidy"],
            ["mock-clang-format", "mock-lint-flake8", "coverage"],
            ["dummy", "mock-clang-format", "mock-lint-flake8"],
        ),
        # Skip clang-tidy and mozlint
        (
            ["mock-clang-format", "mock-clang-tidy"],
            ["mock-lint-flake8", "coverage"],
            ["dummy", "mock-lint-flake8"],
        ),
    ],
)
def test_phabricator_analyzers(
    analyzers_skipped,
    valid_issues,
    valid_patches,
    mock_config,
    mock_phabricator,
    mock_try_task,
    mock_decision_task,
    mock_task,
):
    """
    Test analyzers filtering on phabricator reporter
    """
    with mock_phabricator as api:
        # Skip commenting on phabricator
        # we only care about filtering issues
        api.comment = unittest.mock.Mock(return_value=True)

        # Always use the same setup, only varies the analyzers
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)
        revision.lines = {"test.cpp": [0, 41, 42, 43], "dom/test.cpp": [42]}
        revision.id = 52
        reporter = PhabricatorReporter(
            {"analyzers_skipped": analyzers_skipped}, api=api
        )

    issues = [
        ClangFormatIssue(
            mock_task(ClangFormatTask, "mock-clang-format"),
            "dom/test.cpp",
            [
                (41, 41, b"no change"),
                (42, None, b"deletion"),
                (None, 42, b"change here"),
            ],
            revision,
        ),
        ClangTidyIssue(
            mock_task(ClangTidyTask, "mock-clang-tidy"),
            revision,
            "test.cpp",
            "42",
            "51",
            "modernize-use-nullptr",
            "dummy message",
        ),
        MozLintIssue(
            mock_task(MozLintTask, "mock-lint-flake8"),
            "test.cpp",
            1,
            "error",
            42,
            "flake8",
            "Python error",
            "EXXX",
            revision,
        ),
        CoverageIssue(
            mock_task(ZeroCoverageTask, "coverage"),
            "test.cpp",
            0,
            "This file is uncovered",
            revision,
        ),
    ]

    assert all(i.is_publishable() for i in issues)

    revision.improvement_patches = [
        ImprovementPatch(mock_task(DefaultTask, "dummy"), repr(revision), "Whatever"),
        ImprovementPatch(
            mock_task(ClangTidyTask, "mock-clang-tidy"), repr(revision), "Some C fixes"
        ),
        ImprovementPatch(
            mock_task(ClangFormatTask, "mock-clang-format"),
            repr(revision),
            "Some lint fixes",
        ),
        ImprovementPatch(
            mock_task(MozLintTask, "mock-lint-flake8"), repr(revision), "Some js fixes"
        ),
    ]
    list(map(lambda p: p.write(), revision.improvement_patches))  # trigger local write

    issues, patches = reporter.publish(issues, revision, [], [], [])

    # Check issues & patches analyzers
    assert len(issues) == len(valid_issues)
    assert len(patches) == len(valid_patches)
    assert [i.analyzer.name for i in issues] == valid_issues
    assert [p.analyzer.name for p in patches] == valid_patches


def test_phabricator_clang_tidy_build_error(
    mock_phabricator, phab, mock_try_task, mock_decision_task, mock_task
):
    """
    Test Phabricator Lint for a ClangTidyIssue with build error
    """

    from code_review_bot import Level

    with mock_phabricator as api:
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)
        revision.lines = {
            # Add dummy lines diff
            "test.cpp": [41, 42, 43]
        }
        revision.id = 52
        revision.build_target_phid = "PHID-HMBD-deadbeef12456"

        reporter = PhabricatorReporter({}, api=api)

        issue = ClangTidyIssue(
            analyzer=mock_task(ClangTidyTask, "mock-clang-tidy"),
            revision=revision,
            path="dom/animation/Animation.cpp",
            line=57,
            column=46,
            check="clang-diagnostic-error",
            level=Level.Error,
            message="Some Error Message",
            publish=True,
        )

        assert issue.is_publishable()

        issues, patches = reporter.publish([issue], revision, [], [], [])
        assert len(issues) == 1
        assert len(patches) == 0

        # Check the callback has been used
        assert phab.build_messages["PHID-HMBD-deadbeef12456"] == [
            {
                "receiver": "PHID-HMBD-deadbeef12456",
                "lint": [
                    {
                        "code": "clang-diagnostic-error",
                        "description": "(IMPORTANT) ERROR: Some Error Message",
                        "line": 57,
                        "char": 46,
                        "name": "Build Error",
                        "path": "dom/animation/Animation.cpp",
                        "severity": "error",
                    }
                ],
                "type": "work",
                "unit": [],
            }
        ]
        assert phab.comments[51] == [VALID_BUILD_ERROR_MESSAGE]


def test_full_file(
    mock_config, mock_phabricator, phab, mock_try_task, mock_decision_task, mock_task
):
    """
    Test Phabricator reporter supports an issue on a full file
    """

    with mock_phabricator as api:
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)
        revision.lines = {
            # Add dummy lines diff
            "xx.cpp": [123, 124, 125]
        }
        revision.files = list(revision.lines.keys())
        revision.id = 52
        reporter = PhabricatorReporter(api=api)

    issue = DefaultIssue(
        analyzer=mock_task(DefaultTask, "full-file-analyzer"),
        revision=revision,
        path="xx.cpp",
        line=-1,
        nb_lines=0,
        check="a-huge-issue",
        message="Something bad happened on the whole file !",
    )
    assert issue.line is None  # check auto conversion
    assert (
        str(issue) == "full-file-analyzer issue a-huge-issue@warning xx.cpp full file"
    )
    assert issue.is_publishable()
    assert revision.has_file(issue.path)
    assert revision.contains(issue)

    issues, patches = reporter.publish([issue], revision, [], [], [])
    assert len(issues) == 1
    assert len(patches) == 0

    # Check the comment callback has been used
    assert phab.comments[51] == [
        VALID_DEFAULT_MESSAGE.format(results=mock_config.taskcluster.results_dir)
    ]

    # Check the inline callback has been used
    assert phab.build_messages["PHID-HMBT-test"] == [
        {
            "receiver": "PHID-HMBT-test",
            "lint": [
                {
                    "code": "a-huge-issue",
                    "description": "WARNING: Something bad happened on the "
                    "whole file !",
                    "line": 1,
                    "name": "full-file-analyzer",
                    "path": "xx.cpp",
                    "severity": "warning",
                }
            ],
            "type": "work",
            "unit": [],
        }
    ]


def test_task_failures(mock_phabricator, phab, mock_try_task, mock_decision_task):
    """
    Test Phabricator reporter publication with some task failures
    """

    with mock_phabricator as api:
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)
        revision.id = 52
        reporter = PhabricatorReporter({"analyzers": ["clang-tidy"]}, api=api)

    status = {
        "task": {"metadata": {"name": "mock-clang-tidy"}},
        "status": {"runs": [{"runId": 0}]},
    }
    task = ClangTidyTask("ab3NrysvSZyEwsOHL2MZfw", status)
    issues, patches = reporter.publish([], revision, [task], [], [])
    assert len(issues) == 0
    assert len(patches) == 0

    # Check the callback has been used to post comments
    assert phab.comments[51] == [VALID_TASK_FAILURES_MESSAGE]


def test_extra_errors(
    mock_phabricator, mock_try_task, mock_decision_task, phab, mock_task
):
    """
    Test Phabricator reporter publication with some errors outside of patch
    """

    with mock_phabricator as api:
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)
        revision.lines = {"path/to/file.py": [1, 2, 3]}
        revision.files = ["path/to/file.py"]
        revision.id = 52
        reporter = PhabricatorReporter({}, api=api)

    task = mock_task(MozLintTask, "source-test-mozlint-dummy")
    all_issues = [
        # Warning in patch
        MozLintIssue(
            analyzer=task,
            path="path/to/file.py",
            column=25,
            level=Level.Warning,
            lineno=2,
            linter="flake8",
            message="Some not so bad python mistake",
            check="EYYY",
            revision=revision,
        ),
        # Error outside of patch
        MozLintIssue(
            analyzer=task,
            path="path/to/file.py",
            column=12,
            level=Level.Error,
            lineno=10,
            linter="flake8",
            message="Some bad python typo",
            check="EXXX",
            revision=revision,
        ),
        # Warning outside of patch
        MozLintIssue(
            analyzer=task,
            path="path/to/file.py",
            column=1,
            level=Level.Warning,
            lineno=25,
            linter="flake8",
            message="Random mistake that will be ignored",
            check="EZZZ",
            revision=revision,
        ),
    ]

    published_issues, patches = reporter.publish(all_issues, revision, [], [], [])
    assert len(published_issues) == 2
    assert len(patches) == 0

    # Check the callbacks have been used to publish:
    # - a top comment to summarize issues
    # - a lint result for the error outside of patch
    # - a lint result for the warning inside patch
    assert phab.build_messages["PHID-HMBT-test"] == [
        {
            "receiver": "PHID-HMBT-test",
            "lint": [
                {
                    "char": 25,
                    "code": "EYYY",
                    "description": "WARNING: Some not so bad python mistake",
                    "line": 2,
                    "name": "dummy (Mozlint)",
                    "path": "path/to/file.py",
                    "severity": "warning",
                },
                {
                    "char": 12,
                    "code": "EXXX",
                    "description": "(IMPORTANT) ERROR: Some bad python typo",
                    "line": 10,
                    "name": "dummy (Mozlint)",
                    "path": "path/to/file.py",
                    "severity": "error",
                },
            ],
            "unit": [],
            "type": "work",
        }
    ]

    assert phab.comments[51] == [VALID_MOZLINT_MESSAGE]


def test_phabricator_notices(mock_phabricator, phab, mock_try_task, mock_decision_task):
    """
    Test Phabricator reporter publication on a mock clang-format issue
    """

    with mock_phabricator as api:
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)
        revision.lines = {
            # Add dummy lines diff
            "test.rst": [41, 42, 43],
        }
        revision.id = 52
        reporter = PhabricatorReporter({"analyzers": ["doc-upload"]}, api=api)

    doc_url = "http://gecko-docs.mozilla.org-l1.s3-website.us-west-2.amazonaws.com/59dc75b0-e207-11ea-8fa5-0242ac110004/index.html"
    notices = [COMMENT_LINK_TO_DOC.format(diff_id=42, doc_url=doc_url)]
    reporter.publish(
        [],
        revision,
        [],
        notices,
        [],
    )

    # Check the comment has been posted
    assert phab.comments[51] == [VALID_NOTICE_MESSAGE.format(notice=notices[0].strip())]

    # Test a comment with multiple notices
    link = "[diff](http://example.com/diff.txt)"
    notices.append(
        COMMENT_TASKGRAPH_DIFF.format(diff_id=42, s="", have="has", markdown_links=link)
    )

    phab.comments[51] = []
    reporter.publish(
        [],
        revision,
        [],
        notices,
        [],
    )

    # Check the comment has been posted
    assert phab.comments[51] == [
        VALID_NOTICE_MESSAGE.format(notice="\n\n---\n".join(notices).strip())
    ]


def test_phabricator_tgdiff(mock_phabricator, phab, mock_try_task, mock_decision_task):
    """
    Test Phabricator reporter publication on a mock clang-format issue
    """

    with mock_phabricator as api:
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)
        revision.lines = {
            # Add dummy lines diff
            "test.rst": [41, 42, 43],
        }
        revision.id = 52
        reporter = PhabricatorReporter({"analyzers": ["doc-upload"]}, api=api)

    doc_url = "http://gecko-docs.mozilla.org-l1.s3-website.us-west-2.amazonaws.com/59dc75b0-e207-11ea-8fa5-0242ac110004/index.html"
    doc_notice = COMMENT_LINK_TO_DOC.format(diff_id=42, doc_url=doc_url)

    reporter.publish(
        [],
        revision,
        [],
        [doc_notice],
        ["taskgraph-reviewers"],
    )

    # Check the reviewer group has been added to the revision
    assert phab.transactions[51] == [
        [{"type": "reviewers.add", "value": ["PHID-123456789-TGReviewers"]}]
    ]

    # Check the comment has been posted
    assert phab.comments[51] == [VALID_NOTICE_MESSAGE.format(notice=doc_notice.strip())]


def test_phabricator_external_tidy(
    mock_phabricator, phab, mock_try_task, mock_decision_task, mock_task
):
    """
    Test Phabricator reporter publication on a mock external-tidy issue
    """

    with mock_phabricator as api:
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)
        revision.lines = {
            # Add dummy lines diff
            "another_test.cpp": [41, 42, 43]
        }
        revision.files = ["another_test.cpp"]
        revision.id = 52
        reporter = PhabricatorReporter({"analyzers": ["clang-tidy-external"]}, api=api)

    issue_clang_diagnostic = ExternalTidyIssue(
        mock_task(ExternalTidyTask, "source-test-clang-external"),
        revision,
        "another_test.cpp",
        "42",
        "51",
        "clang-diagnostic-unused-variable",
        "dummy message",
        publish=False,
    )
    issue_civet_warning = ExternalTidyIssue(
        mock_task(ExternalTidyTask, "source-test-clang-external"),
        revision,
        "another_test.cpp",
        "43",
        "9",
        "mozilla-civet-private-checker-1",
        "dummy message",
        publish=True,
    )

    assert issue_civet_warning.is_publishable()
    assert not issue_clang_diagnostic.is_publishable()

    issues, patches = reporter.publish(
        [issue_civet_warning, issue_clang_diagnostic], revision, [], [], []
    )
    assert len(issues) == 1
    assert len(patches) == 0

    # Check the comment has been posted
    assert phab.comments[51] == [VALID_EXTERNAL_TIDY_MESSAGE]


def test_phabricator_newer_diff(
    mock_phabricator, phab, mock_try_task, mock_decision_task, mock_task
):
    """
    Test Phabricator reporter publication won't be called when a newer diff exists for the patch
    """

    with mock_phabricator as api:
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)
        revision.lines = {
            # Add dummy lines diff
            "test.txt": [0],
            "path/to/test.cpp": [0],
            "dom/test.cpp": [42],
        }
        reporter = PhabricatorReporter({"analyzers": ["coverage"]}, api=api)

    issue = CoverageIssue(
        mock_task(ZeroCoverageTask, "coverage"),
        "path/to/test.cpp",
        0,
        "This file is uncovered",
        revision,
    )
    assert issue.is_publishable()

    with capture_logs() as cap_logs:
        os.environ["SPECIAL_NAME"] = "PHID-DREV-zzzzz-updated"

        issues, patches = reporter.publish([issue], revision, [], [], [])

        assert cap_logs == [
            # Log from PhabricatorReporter.publish_harbormaster(), it was still called
            {
                "event": "Updated Harbormaster build state with issues",
                "log_level": "info",
                "nb_lint": 1,
                "nb_unit": 0,
            },
            {
                "event": "A newer diff exists on this patch, skipping the comment publication",
                "log_level": "warning",
            },
        ]

    assert len(issues) == 1
    assert len(patches) == 0

    # Check the lint results
    assert phab.build_messages["PHID-HMBT-test"] == [
        {
            "receiver": "PHID-HMBT-test",
            "lint": [
                {
                    "code": "no-coverage",
                    "description": "WARNING: This file is uncovered",
                    "line": 1,
                    "name": "code coverage analysis",
                    "path": "path/to/test.cpp",
                    "severity": "warning",
                }
            ],
            "type": "work",
            "unit": [],
        }
    ]

    # Check the comment hasn't been posted
    assert phab.comments[51] == []

    # Clear the environment
    del os.environ["SPECIAL_NAME"]


def test_phabricator_former_diff_comparison(
    monkeypatch, mock_phabricator, phab, mock_try_task, mock_decision_task, mock_task
):
    """
    Test Phabricator reporter publication shows the number of unresolved
    and closed issues compared to the previous diff.
    In this test, 2 issues are detected. 1 is new, 1 is unresolved and 2
    issues from the previous diff have been closed.
    """

    with mock_phabricator as api:
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)
        revision.lines = {
            # Add dummy lines diff
            "test.txt": [0],
            "path/to/test.cpp": [0],
            "dom/test.cpp": [42],
        }
        revision.id = 52
        reporter = PhabricatorReporter({"analyzers": ["coverage"]}, api=api)

    issues = [
        CoverageIssue(
            mock_task(ZeroCoverageTask, "coverage"),
            "path/to/test.cpp",
            0,
            "This file is uncovered",
            revision,
        ),
        ClangFormatIssue(
            mock_task(ClangFormatTask, "source-test-clang-format"),
            "dom/test.cpp",
            [(42, 42, b"That line is wrong. Good luck debugging")],
            revision,
        ),
    ]
    assert all(issue.is_publishable() for issue in issues)
    for i, issue in enumerate(issues, start=1):
        issue.on_backend = {
            "hash": f"hash0{i}",
            "publishable": True,
        }

    # Mock a paginated backend response
    backend = "code-review-backend.test"
    responses.add(
        responses.GET,
        f"http://{backend}/v1/diff/41/issues/",
        json={
            "count": 2,
            "previous": None,
            "next": f"http://{backend}/v1/diff/41/issues/?page=2",
            "results": [
                {
                    "id": "issue 1",
                    "hash": "hash02",
                }
            ],
        },
    )
    responses.add(
        responses.GET,
        f"http://{backend}/v1/diff/41/issues/?page=2",
        json={
            "count": 2,
            "previous": f"http://{backend}/v1/diff/41/issues/",
            "next": None,
            "results": [
                {
                    "id": "issue 2",
                    "hash": "hash03",
                }
            ],
        },
    )

    reporter.api.search_diffs = lambda revision_phid: [
        {"id": 39},
        {"id": 41},
        {"id": 42},
    ]

    os.environ["SPECIAL_NAME"] = "PHID-DREV-zzzzz-updated"

    with capture_logs() as cap_logs:
        issues, patches = reporter.publish(issues, revision, [], [], [])

    assert cap_logs == [
        # Log from PhabricatorReporter.publish_harbormaster(), it was still called
        {
            "event": "Updated Harbormaster build state with issues",
            "log_level": "info",
            "nb_lint": 2,
            "nb_unit": 0,
        },
        {
            "event": "Published phabricator summary",
            "log_level": "info",
        },
    ]

    # Check the lint results
    assert phab.build_messages["PHID-HMBT-test"] == [
        {
            "receiver": "PHID-HMBT-test",
            "lint": [
                {
                    "code": "no-coverage",
                    "description": "WARNING: This file is uncovered",
                    "line": 1,
                    "name": "code coverage analysis",
                    "path": "path/to/test.cpp",
                    "severity": "warning",
                },
                {
                    "code": "invalid-styling",
                    "description": (
                        "WARNING: The change does not follow the C/C++ "
                        "coding style, please reformat\n\n"
                        "  lang=c++\n"
                        "  That line is wrong. Good luck debugging"
                    ),
                    "line": 42,
                    "name": "clang-format",
                    "path": "dom/test.cpp",
                    "severity": "warning",
                },
            ],
            "type": "work",
            "unit": [],
        }
    ]

    assert phab.comments[51] == [FOLLOW_UP_DIFF_MESSAGE]

    # Clear the environment
    del os.environ["SPECIAL_NAME"]


def test_phabricator_before_after_comment(
    monkeypatch,
    mock_phabricator,
    phab,
    mock_try_task,
    mock_decision_task,
    mock_task,
    mock_taskcluster_config,
):
    """
    Test Phabricator reporter publication shows all type of issues depending on their existence
    on the backend while running the before/after feature.

    Two warnings are detected, one is reported because it is a new issue while the other one
    is marked as existing on the backend (resumed by a line in the footer).
    """
    mock_taskcluster_config.secrets = {"BEFORE_AFTER_RATIO": 1}

    with mock_phabricator as api:
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)
        revision.lines = {
            # Add dummy lines diff
            "test.txt": [0],
            "path/to/test.cpp": [0],
            "dom/test.cpp": [42],
        }
        revision.id = 52
        reporter = PhabricatorReporter({"analyzers": ["coverage"]}, api=api)

    assert revision.before_after_feature is True

    # A new warning issue outside of the patch
    clang_issue = ClangFormatIssue(
        mock_task(ClangFormatTask, "source-test-clang-format"),
        "outside/of/the/patch.cpp",
        [(42, 42, b"That line is wrong. Good luck debugging")],
        revision,
    )
    clang_issue.validates = lambda: True
    clang_issue.new_issue = True
    # A warning already existing on the mozilla-central repository
    cov_issue = CoverageIssue(
        mock_task(ZeroCoverageTask, "coverage"),
        "outside/of/the/patch.txt",
        42,
        "Coverage warning",
        revision,
    )

    # New issues are publishable by default
    assert clang_issue.is_publishable() is True
    assert cov_issue.is_publishable() is False

    # Tag the coverage issue as a new issue (nor unresolved nor closed)
    reporter.compare_issues = lambda former_diff, issues: ([], [])

    with capture_logs() as cap_logs:
        issues, patches = reporter.publish(
            [cov_issue, clang_issue], revision, [], [], []
        )

    assert cap_logs == [
        {
            "event": "Updated Harbormaster build state with issues",
            "log_level": "info",
            "nb_lint": 1,
            "nb_unit": 0,
        },
        {
            "event": "Published phabricator summary",
            "log_level": "info",
        },
    ]

    # Check the lint results
    assert phab.build_messages["PHID-HMBT-test"] == [
        {
            "receiver": "PHID-HMBT-test",
            "lint": [
                {
                    "code": "invalid-styling",
                    "description": (
                        "WARNING: The change does not follow the C/C++ "
                        "coding style, please reformat\n\n"
                        "  lang=c++\n"
                        "  That line is wrong. Good luck debugging"
                    ),
                    "line": 42,
                    "name": "clang-format",
                    "path": "outside/of/the/patch.cpp",
                    "severity": "warning",
                },
            ],
            "type": "work",
            "unit": [],
        }
    ]

    assert phab.comments[51] == [VALID_CLANG_BEFORE_AFTER_MESSAGE]
