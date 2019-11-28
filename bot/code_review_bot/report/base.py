# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import itertools
import urllib.parse

from code_review_bot.tasks.clang_format import ClangFormatIssue
from code_review_bot.tasks.clang_tidy import ClangTidyIssue
from code_review_bot.tasks.coverity import CoverityIssue
from code_review_bot.tasks.default import DefaultIssue
from code_review_bot.tasks.infer import InferIssue
from code_review_bot.tasks.lint import MozLintIssue

COMMENT_PARTS = {
    ClangTidyIssue: {
        "defect": " - {nb} found by clang-tidy",
        "analyzer": " - `./mach static-analysis check {files}` (C/C++)",
    },
    InferIssue: {
        "defect": " - {nb} found by infer",
        "analyzer": " - `./mach static-analysis check-java path/to/file.java` (Java)",
    },
    CoverityIssue: {"defect": " - {nb} found by Coverity"},
    ClangFormatIssue: {
        "defect": " - {nb} found by clang-format",
        "analyzer": " - `./mach clang-format -s -p {files}` (C/C++)",
    },
    MozLintIssue: {
        "defect": " - {nb} found by mozlint",
        "analyzer": " - `./mach lint --warnings path/to/file` (JS/Python/etc)",
    },
    DefaultIssue: {"defect": " - {nb} found by a generic analyzer"},
}
COMMENT_FAILURE = """
Code analysis found {defects_total} in the diff {diff_id}:
"""
COMMENT_RUN_ANALYZERS = """
You can run this analysis locally with:
{analyzers}
"""
COMMENT_COVERAGE = """
In our previous code coverage analysis run, we found some files which had no coverage and are being modified in this patch:
{paths}

Should they have tests, or are they dead code ?

 - You can file a bug blocking [Bug 1415824](https://bugzilla.mozilla.org/show_bug.cgi?id=1415824) for untested files that should be **tested**.
 - You can file a bug blocking [Bug 1415819](https://bugzilla.mozilla.org/show_bug.cgi?id=1415819) for untested files that should be **removed**.
"""
BUG_REPORT = """
If you see a problem in this automated review, [please report it here]({bug_report_url}).
"""
COMMENT_DIFF_DOWNLOAD = """
For your convenience, [here is a patch]({url}) that fixes all the {analyzer} defects (use it in your repository with `hg import` or `git apply -p0`).
"""
COMMENT_TASK_FAILURE = """
The analysis task [{name}](https://firefox-ci-tc.services.mozilla.com/tasks/{task_id}) failed, but we could not detect any issue.
Please check this task manually.
"""


class Reporter(object):
    """
    Common interface to post reports on a website
    Will configure & build reports
    """

    def __init__(self, configuration):
        """
        Configure reporter using Taskcluster credentials and configuration
        """
        raise NotImplementedError

    def publish(self, issues, revision):
        """
        Publish a new report
        """
        raise NotImplementedError

    def requires(self, configuration, *keys):
        """
        Check all configuration necessary keys are present
        """
        assert isinstance(configuration, dict)

        out = []
        for key in keys:
            assert key in configuration, "Missing {} {}".format(
                self.__class__.__name__, key
            )
            out.append(configuration[key])

        return out

    def calc_stats(self, issues):
        """
        Calc stats about issues:
        * group issues by class name
        * count their total number
        * count their publishable number
        """
        groups = itertools.groupby(
            sorted(issues, key=lambda x: str(x.__class__)), lambda x: x.__class__
        )

        def stats(items):
            _items = list(items)
            return {
                "total": len(_items),
                "publishable": sum([i.is_publishable() for i in _items]),
                "publishable_paths": list(
                    {i.path for i in _items if i.is_publishable()}
                ),
            }

        from collections import OrderedDict

        return OrderedDict([(cls, stats(items)) for cls, items in groups])

    def build_comment(
        self, revision, issues, bug_report_url, patches=[], task_failures=[]
    ):
        """
        Build a Markdown comment about published issues
        """

        def pluralize(word, nb):
            assert isinstance(word, str)
            assert isinstance(nb, int)
            return "{} {}".format(nb, nb == 1 and word or word + "s")

        # Calc stats for issues, grouped by class
        stats = self.calc_stats(issues)

        # Build parts depending on issues
        defects, analyzers = [], []
        for cls, cls_stats in stats.items():
            part = COMMENT_PARTS.get(cls)
            assert part is not None, "Unsupported issue class {}".format(cls)
            defects.append(
                part["defect"].format(nb=pluralize("defect", cls_stats["publishable"]))
            )
            if "analyzer" in part:
                analyzers.append(
                    part["analyzer"].format(
                        files=" ".join(cls_stats["publishable_paths"])
                    )
                )

        # Build top comment
        nb = len(issues)

        if nb > 0:
            comment = COMMENT_FAILURE.format(
                defects_total=pluralize("defect", nb), diff_id=revision.diff_id
            )
        else:
            comment = ""

        # Add defects
        if defects:
            comment += "\n".join(defects) + "\n"

        if analyzers:
            comment += COMMENT_RUN_ANALYZERS.format(analyzers="\n".join(analyzers))

        for patch in patches:
            comment += COMMENT_DIFF_DOWNLOAD.format(
                analyzer=patch.analyzer, url=patch.url or patch.path
            )

        for task in task_failures:
            comment += COMMENT_TASK_FAILURE.format(name=task.name, task_id=task.id)

        assert comment != "", "Empty comment"

        comment += BUG_REPORT.format(bug_report_url=bug_report_url)

        return comment

    def build_coverage_comment(self, issues, bug_report_url):
        """
        Build a Markdown comment about coverage-related issues
        """

        def coverage_url(path):
            path = urllib.parse.quote_plus(path)
            return f"https://coverage.moz.tools/#revision=latest&path={path}&view=file"

        comment = COMMENT_COVERAGE.format(
            paths="\n".join(
                f" - [{issue.path}]({coverage_url(issue.path)})" for issue in issues
            )
        )

        comment += BUG_REPORT.format(bug_report_url=bug_report_url)

        return comment
