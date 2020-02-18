# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import itertools
import re
import urllib.parse
from typing import Pattern

from code_review_tools import treeherder

HELP_COMMANDS = {
    "source-test-clang-tidy": " - `./mach static-analysis check {files}` (C/C++)",
    "source-test-infer-infer": " - `./mach static-analysis check-java path/to/file.java` (Java)",
    "source-test-clang-format": " - `./mach clang-format -s -p {files}` (C/C++)",
    re.compile(
        "^source-test-mozlint-.*"
    ): " - `./mach lint --warnings path/to/file` (JS/Python/etc)",
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
The analysis task [{name}]({url}) failed, but we could not detect any issue.
Please check this task manually.
"""
FRONTEND_LINK = """
You can view [these defects]({url}) on the code-review frontend.
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
        * group issues by analyzer
        * count their total number
        * count their publishable number
        """

        groups = itertools.groupby(
            sorted(issues, key=lambda i: i.analyzer), lambda i: i.analyzer
        )

        def stats(analyzer, items):
            _items = list(items)

            # Lookup the help message, supporting regexes
            _help = HELP_COMMANDS.get(analyzer)
            if _help is None:
                for regex, help_value in HELP_COMMANDS.items():
                    if isinstance(regex, Pattern) and regex.match(analyzer):
                        assert (
                            _help is None
                        ), f"Duplicate help command found for {analyzer}"
                        _help = help_value

            # Strip source-test- to get cleaner names
            if analyzer.startswith("source-test-"):
                analyzer = analyzer[12:]

            return {
                "analyzer": analyzer,
                "help": _help,
                "total": len(_items),
                "publishable": sum([i.is_publishable() for i in _items]),
                "publishable_paths": list(
                    {i.path for i in _items if i.is_publishable()}
                ),
            }

        return [stats(analyzer, items) for analyzer, items in groups]

    def build_comment(
        self,
        revision,
        issues,
        bug_report_url,
        patches=[],
        task_failures=[],
        frontend_url=None,
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
        for stat in stats:
            defects.append(
                " - {nb} found by {analyzer}".format(
                    analyzer=stat["analyzer"],
                    nb=pluralize("defect", stat["publishable"]),
                )
            )
            _help = stat.get("help")
            if _help is not None:
                analyzers.append(
                    _help.format(files=" ".join(stat["publishable_paths"]))
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
            treeherder_url = treeherder.get_job_url(
                task.id, task.run_id, revision=revision.mercurial_revision
            )
            comment += COMMENT_TASK_FAILURE.format(name=task.name, url=treeherder_url)

        assert comment != "", "Empty comment"

        comment += BUG_REPORT.format(bug_report_url=bug_report_url)

        if defects and frontend_url:
            comment += FRONTEND_LINK.format(url=frontend_url)

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
