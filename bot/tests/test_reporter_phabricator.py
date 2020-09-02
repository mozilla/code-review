# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import unittest

import pytest

from code_review_bot import Level
from code_review_bot.report.phabricator import PhabricatorReporter
from code_review_bot.revisions import ImprovementPatch
from code_review_bot.revisions import Revision
from code_review_bot.tasks.clang_format import ClangFormatIssue
from code_review_bot.tasks.clang_format import ClangFormatTask
from code_review_bot.tasks.clang_tidy import ClangTidyIssue
from code_review_bot.tasks.clang_tidy import ClangTidyTask
from code_review_bot.tasks.coverage import CoverageIssue
from code_review_bot.tasks.coverage import ZeroCoverageTask
from code_review_bot.tasks.coverity import CoverityIssue
from code_review_bot.tasks.coverity import CoverityTask
from code_review_bot.tasks.default import DefaultIssue
from code_review_bot.tasks.default import DefaultTask
from code_review_bot.tasks.infer import InferIssue
from code_review_bot.tasks.infer import InferTask
from code_review_bot.tasks.lint import MozLintIssue
from code_review_bot.tasks.lint import MozLintTask

VALID_CLANG_TIDY_MESSAGE = """
Code analysis found 1 defect in the diff 42:
 - 1 defect found by clang-tidy

You can run this analysis locally with:
 - `./mach static-analysis check --outgoing` (C/C++)

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).

You can view these defects on [the code-review frontend](https://code-review.moz.tools/#/diff/42) and on [Treeherder](https://treeherder.mozilla.org/#/jobs?repo=try&revision=deadbeef1234).
"""

VALID_COVERITY_MESSAGE = """
Code analysis found 1 defect in the diff 42:
 - 1 defect found by Coverity

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).

You can view these defects on [the code-review frontend](https://code-review.moz.tools/#/diff/42) and on [Treeherder](https://treeherder.mozilla.org/#/jobs?repo=try&revision=deadbeef1234).
"""

VALID_BUILD_ERROR_MESSAGE = """
Code analysis found 1 defect in the diff 42:
 - 1 build error found by clang-tidy

You can run this analysis locally with:
 - `./mach static-analysis check --outgoing` (C/C++)

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).

You can view these defects on [the code-review frontend](https://code-review.moz.tools/#/diff/42) and on [Treeherder](https://treeherder.mozilla.org/#/jobs?repo=try&revision=deadbeef1234).
"""

VALID_CLANG_FORMAT_MESSAGE = """
Code analysis found 1 defect in the diff 42:
 - 1 defect found by clang-format

You can run this analysis locally with:
 - `./mach clang-format -s -p dom/test.cpp` (C/C++)

For your convenience, [here is a patch]({results}/source-test-clang-format-PHID-DIFF-test.diff) that fixes all the clang-format defects (use it in your repository with `hg import` or `git apply -p0`).

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).

You can view these defects on [the code-review frontend](https://code-review.moz.tools/#/diff/42) and on [Treeherder](https://treeherder.mozilla.org/#/jobs?repo=try&revision=deadbeef1234).
"""


VALID_FLAKE8_MESSAGE = """
Code analysis found 2 defects in the diff 42:
 - 1 defect found by eslint (Mozlint)
 - 1 defect found by py-flake8 (Mozlint)

You can run this analysis locally with:
 - `./mach lint --warnings --outgoing`

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).

You can view these defects on [the code-review frontend](https://code-review.moz.tools/#/diff/42) and on [Treeherder](https://treeherder.mozilla.org/#/jobs?repo=try&revision=deadbeef1234).
"""


VALID_COVERAGE_MESSAGE = """
Code analysis found 1 defect in the diff 42:
 - 1 defect found by code coverage analysis

In our previous code coverage analysis run, we found some files which had no coverage and are being modified in this patch:
Should they have tests, or are they dead code?

 - You can file a bug blocking [Bug 1415824](https://bugzilla.mozilla.org/show_bug.cgi?id=1415824) for untested files that should be **tested**.
 - You can file a bug blocking [Bug 1415819](https://bugzilla.mozilla.org/show_bug.cgi?id=1415819) for untested files that should be **removed**.

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).

You can view these defects on [the code-review frontend](https://code-review.moz.tools/#/diff/42) and on [Treeherder](https://treeherder.mozilla.org/#/jobs?repo=try&revision=deadbeef1234).
"""

VALID_DEFAULT_MESSAGE = """
Code analysis found 1 defect in the diff 42:
 - 1 defect found by full-file-analyzer

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).

You can view these defects on [the code-review frontend](https://code-review.moz.tools/#/diff/42) and on [Treeherder](https://treeherder.mozilla.org/#/jobs?repo=try&revision=deadbeef1234).
"""

VALID_TASK_FAILURES_MESSAGE = """
The analysis task [mock-infer](https://treeherder.mozilla.org/#/jobs?repo=try&revision=aabbccddee&selectedTaskRun=ab3NrysvSZyEwsOHL2MZfw-0) failed, but we could not detect any issue.
Please check this task manually.

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).
"""


VALID_MOZLINT_MESSAGE = """
Code analysis found 2 defects in the diff 42:
 - 2 defects found by dummy (Mozlint)

You can run this analysis locally with:
 - `./mach lint --warnings --outgoing`

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).

You can view these defects on [the code-review frontend](https://code-review.moz.tools/#/diff/42) and on [Treeherder](https://treeherder.mozilla.org/#/jobs?repo=try&revision=deadbeef1234).
"""

VALID_CLANG_TIDY_COVERAGE_MESSAGE = """
Code analysis found 2 defects in the diff 42:
 - 1 defect found by clang-tidy
 - 1 defect found by code coverage analysis

You can run this analysis locally with:
 - `./mach static-analysis check --outgoing` (C/C++)

In our previous code coverage analysis run, we found some files which had no coverage and are being modified in this patch:
Should they have tests, or are they dead code?

 - You can file a bug blocking [Bug 1415824](https://bugzilla.mozilla.org/show_bug.cgi?id=1415824) for untested files that should be **tested**.
 - You can file a bug blocking [Bug 1415819](https://bugzilla.mozilla.org/show_bug.cgi?id=1415819) for untested files that should be **removed**.

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).

You can view these defects on [the code-review frontend](https://code-review.moz.tools/#/diff/42) and on [Treeherder](https://treeherder.mozilla.org/#/jobs?repo=try&revision=deadbeef1234).
"""

VALID_DOC_UPLOAD_MESSAGE = """
We think you might have touched the doc files, generated doc can be accessed [here](http://gecko-docs.mozilla.org-l1.s3-website.us-west-2.amazonaws.com/59dc75b0-e207-11ea-8fa5-0242ac110004/index.html).

If you see a problem in this automated review, [please report it here](https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__).
"""


def test_phabricator_clang_tidy(mock_phabricator, phab, mock_try_task, mock_task):
    """
    Test Phabricator reporter publication on a mock clang-tidy issue
    """

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.mercurial_revision = "deadbeef1234"
        revision.repository = "https://hg.mozilla.org/try"
        revision.repository_try_name = "try"
        revision.lines = {
            # Add dummy lines diff
            "another_test.cpp": [41, 42, 43]
        }
        revision.files = ["another_test.cpp"]
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

    issues, patches = reporter.publish([issue], revision, [])
    assert len(issues) == 1
    assert len(patches) == 0

    # Check the comment has been posted
    assert phab.comments[51] == [VALID_CLANG_TIDY_MESSAGE]


def test_phabricator_clang_format(
    mock_config, mock_phabricator, phab, mock_try_task, mock_task
):
    """
    Test Phabricator reporter publication on a mock clang-format issue
    """

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.mercurial_revision = "deadbeef1234"
        revision.repository = "https://hg.mozilla.org/try"
        revision.repository_try_name = "try"
        revision.lines = {
            # Add dummy lines diff
            "test.cpp": [41, 42, 43],
            "dom/test.cpp": [42],
        }
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

    issues, patches = reporter.publish([issue], revision, [])
    assert len(issues) == 1
    assert len(patches) == 1

    # Check the comment has been posted
    assert phab.comments[51] == [
        VALID_CLANG_FORMAT_MESSAGE.format(results=mock_config.taskcluster.results_dir)
    ]


def test_phabricator_mozlint(
    mock_config, mock_phabricator, phab, mock_try_task, mock_task
):
    """
    Test Phabricator reporter publication on two mock mozlint issues
    using two different analyzers
    """

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.mercurial_revision = "deadbeef1234"
        revision.repository = "https://hg.mozilla.org/try"
        revision.repository_try_name = "try"
        revision.lines = {
            # Add dummy lines diff
            "python/test.py": [41, 42, 43],
            "js/test.js": [10, 11, 12],
            "dom/test.cpp": [42],
        }
        revision.files = revision.lines.keys()
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

    issues, patches = reporter.publish([issue_flake, issue_eslint], revision, [])
    assert len(issues) == 2
    assert len(patches) == 0

    # Check the callbacks have been used to publish either a lint result + summary comment
    assert phab.comments[51] == [
        VALID_FLAKE8_MESSAGE.format(results=mock_config.taskcluster.results_dir)
    ]
    assert phab.build_messages["PHID-HMBT-test"] == [
        {
            "buildTargetPHID": "PHID-HMBT-test",
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
    mock_config, mock_phabricator, phab, mock_try_task, mock_task
):
    """
    Test Phabricator reporter publication on a mock coverage issue
    """

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.mercurial_revision = "deadbeef1234"
        revision.repository = "https://hg.mozilla.org/try"
        revision.repository_try_name = "try"
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

    issues, patches = reporter.publish([issue], revision, [])
    assert len(issues) == 1
    assert len(patches) == 0

    # Check the lint results
    assert phab.build_messages["PHID-HMBT-test"] == [
        {
            "buildTargetPHID": "PHID-HMBT-test",
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


def test_phabricator_clang_tidy_and_coverage(
    mock_config, mock_phabricator, phab, mock_try_task, mock_task
):
    """
    Test Phabricator reporter publication on a mock coverage issue
    """

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.mercurial_revision = "deadbeef1234"
        revision.repository = "https://hg.mozilla.org/try"
        revision.repository_try_name = "try"
        revision.lines = {
            # Add dummy lines diff
            "test.txt": [0],
            "path/to/test.cpp": [0],
            "another_test.cpp": [41, 42, 43],
        }
        revision.files = ["test.txt", "test.cpp", "another_test.cpp"]
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

    issues, patches = reporter.publish([issue_clang_tidy, issue_coverage], revision, [])
    assert len(issues) == 2
    assert len(patches) == 0

    # Check the lint results
    assert phab.build_messages["PHID-HMBT-test"] == [
        {
            "buildTargetPHID": "PHID-HMBT-test",
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
                "mock-infer",
                "mock-lint-flake8",
                "coverage",
            ],
            [
                "dummy",
                "mock-clang-tidy",
                "mock-clang-format",
                "mock-infer",
                "mock-lint-flake8",
            ],
        ),
        # Skip clang-tidy
        (
            ["mock-clang-tidy"],
            ["mock-clang-format", "mock-infer", "mock-lint-flake8", "coverage"],
            ["dummy", "mock-clang-format", "mock-infer", "mock-lint-flake8"],
        ),
        # Skip clang-tidy and mozlint
        (
            ["mock-clang-format", "mock-clang-tidy"],
            ["mock-infer", "mock-lint-flake8", "coverage"],
            ["dummy", "mock-infer", "mock-lint-flake8"],
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
        revision = Revision.from_try(mock_try_task, api)
        revision.mercurial_revision = "deadbeef1234"
        revision.repository = "https://hg.mozilla.org/try"
        revision.repository_try_name = "try"
        revision.lines = {"test.cpp": [0, 41, 42, 43], "dom/test.cpp": [42]}
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
        InferIssue(
            mock_task(InferTask, "mock-infer"),
            {
                "file": "test.cpp",
                "line": 42,
                "column": 1,
                "bug_type": "dummy",
                "kind": "WARNING",
                "qualifier": "dummy message.",
            },
            revision,
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
            mock_task(InferTask, "mock-infer"), repr(revision), "Some java fixes"
        ),
        ImprovementPatch(
            mock_task(MozLintTask, "mock-lint-flake8"), repr(revision), "Some js fixes"
        ),
    ]
    list(map(lambda p: p.write(), revision.improvement_patches))  # trigger local write

    issues, patches = reporter.publish(issues, revision, [])

    # Check issues & patches analyzers
    assert len(issues) == len(valid_issues)
    assert len(patches) == len(valid_patches)
    assert [i.analyzer.name for i in issues] == valid_issues
    assert [p.analyzer.name for p in patches] == valid_patches


def test_phabricator_coverity(mock_phabricator, phab, mock_try_task, mock_task):
    """
    Test Phabricator Lint for a CoverityIssue
    """

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.lines = {
            # Add dummy lines diff
            "test.cpp": [41, 42, 43]
        }
        revision.build_target_phid = "PHID-HMBD-deadbeef12456"
        revision.repository = "https://hg.mozilla.org/try"
        revision.repository_try_name = "try"
        revision.mercurial_revision = "deadbeef1234"

        reporter = PhabricatorReporter({}, api=api)

        issue_dict = {
            "line": 41,
            "reliability": "medium",
            "message": 'Dereferencing a pointer that might be "nullptr" "env" when calling "lookupImport".',
            "flag": "NULL_RETURNS",
            "build_error": False,
            "extra": {
                "category": "Null pointer dereferences",
                "stateOnServer": {
                    "ownerLdapServerName": "local",
                    "stream": "Firefox",
                    "cid": 95687,
                    "cached": False,
                    "retrievalDateTime": "2019-05-13T10:20:22+00:00",
                    "firstDetectedDateTime": "2019-04-08T12:57:07+00:00",
                    "presentInReferenceSnapshot": False,
                    "components": ["js"],
                    "customTriage": {},
                    "triage": {
                        "fixTarget": "Untargeted",
                        "severity": "Unspecified",
                        "classification": "Unclassified",
                        "owner": "try",
                        "legacy": "False",
                        "action": "Undecided",
                        "externalReference": "",
                    },
                },
            },
        }

        issue = CoverityIssue(
            mock_task(CoverityTask, "mock-coverity"), revision, issue_dict, "test.cpp"
        )
        assert issue.is_publishable()

        issues, patches = reporter.publish([issue], revision, [])
        assert len(issues) == 1
        assert len(patches) == 0

        # Check the callback has been used
        assert phab.build_messages["PHID-HMBD-deadbeef12456"] == [
            {
                "buildTargetPHID": "PHID-HMBD-deadbeef12456",
                "lint": [
                    {
                        "code": "NULL_RETURNS",
                        "description": 'WARNING: Dereferencing a pointer that might be "nullptr" '
                        '"env" when calling "lookupImport".',
                        "line": 41,
                        "name": "Coverity",
                        "path": "test.cpp",
                        "severity": "warning",
                    }
                ],
                "type": "work",
                "unit": [],
            }
        ]
        assert phab.comments[51] == [VALID_COVERITY_MESSAGE]


def test_phabricator_clang_tidy_build_error(
    mock_phabricator, phab, mock_try_task, mock_task
):
    """
    Test Phabricator Lint for a ClangTidyIssue with build error
    """

    from code_review_bot import Level

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.lines = {
            # Add dummy lines diff
            "test.cpp": [41, 42, 43]
        }
        revision.build_target_phid = "PHID-HMBD-deadbeef12456"
        revision.repository = "https://hg.mozilla.org/try"
        revision.repository_try_name = "try"
        revision.mercurial_revision = "deadbeef1234"

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

        issues, patches = reporter.publish([issue], revision, [])
        assert len(issues) == 1
        assert len(patches) == 0

        # Check the callback has been used
        assert phab.build_messages["PHID-HMBD-deadbeef12456"] == [
            {
                "buildTargetPHID": "PHID-HMBD-deadbeef12456",
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


def test_full_file(mock_config, mock_phabricator, phab, mock_try_task, mock_task):
    """
    Test Phabricator reporter supports an issue on a full file
    """

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.mercurial_revision = "deadbeef1234"
        revision.repository = "https://hg.mozilla.org/try"
        revision.repository_try_name = "try"
        revision.lines = {
            # Add dummy lines diff
            "xx.cpp": [123, 124, 125]
        }
        revision.files = list(revision.lines.keys())
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

    issues, patches = reporter.publish([issue], revision, [])
    assert len(issues) == 1
    assert len(patches) == 0

    # Check the comment callback has been used
    assert phab.comments[51] == [
        VALID_DEFAULT_MESSAGE.format(results=mock_config.taskcluster.results_dir)
    ]

    # Check the inline callback has been used
    assert phab.build_messages["PHID-HMBT-test"] == [
        {
            "buildTargetPHID": "PHID-HMBT-test",
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


def test_task_failures(mock_phabricator, phab, mock_try_task):
    """
    Test Phabricator reporter publication with some task failures
    """

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.mercurial_revision = "aabbccddee"
        revision.repository = "https://hg.mozilla.org/try"
        revision.repository_try_name = "try"
        reporter = PhabricatorReporter({"analyzers": ["clang-tidy"]}, api=api)

    status = {
        "task": {"metadata": {"name": "mock-infer"}},
        "status": {"runs": [{"runId": 0}]},
    }
    task = ClangTidyTask("ab3NrysvSZyEwsOHL2MZfw", status)
    issues, patches = reporter.publish([], revision, [task])
    assert len(issues) == 0
    assert len(patches) == 0

    # Check the callback has been used to post comments
    assert phab.comments[51] == [VALID_TASK_FAILURES_MESSAGE]


def test_extra_errors(mock_phabricator, mock_try_task, phab, mock_task):
    """
    Test Phabricator reporter publication with some errors outside of patch
    """

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.mercurial_revision = "deadbeef1234"
        revision.repository = "https://hg.mozilla.org/try"
        revision.repository_try_name = "try"
        revision.lines = {"path/to/file.py": [1, 2, 3]}
        revision.files = ["path/to/file.py"]
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

    published_issues, patches = reporter.publish(all_issues, revision, [])
    assert len(published_issues) == 2
    assert len(patches) == 0

    # Check the callbacks have been used to publish:
    # - a top comment to summarize issues
    # - a lint result for the error outside of patch
    # - a lint result for the warning inside patch
    assert phab.build_messages["PHID-HMBT-test"] == [
        {
            "buildTargetPHID": "PHID-HMBT-test",
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

def test_phabricator_doc_upload(
    mock_config, mock_phabricator, phab, mock_try_task, mock_task
):
    """
    Test Phabricator reporter publication on a mock clang-format issue
    """

    with mock_phabricator as api:
        revision = Revision.from_try(mock_try_task, api)
        revision.mercurial_revision = "deadbeef1234"
        revision.repository = "https://hg.mozilla.org/try"
        revision.repository_try_name = "try"
        revision.lines = {
            # Add dummy lines diff
            "test.rst": [41, 42, 43],
        }
        reporter = PhabricatorReporter({"analyzers": ["doc-upload"]}, api=api)

    reporter.publish([], revision, [], "http://gecko-docs.mozilla.org-l1.s3-website.us-west-2.amazonaws.com/59dc75b0-e207-11ea-8fa5-0242ac110004/index.html")

    # Check the comment has been posted
    assert phab.comments[51] == [VALID_DOC_UPLOAD_MESSAGE]
