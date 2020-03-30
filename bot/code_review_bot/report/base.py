# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import itertools

from code_review_bot.tasks.coverage import CoverageIssue
from code_review_tools import treeherder

COMMENT_FAILURE = """
Code analysis found {defects_total} in the diff {diff_id}:
"""
COMMENT_RUN_ANALYZERS = """
You can run this analysis locally with:
{analyzers}
"""
COMMENT_COVERAGE = """
In our previous code coverage analysis run, we found some files which had no coverage and are being modified in this patch:
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
FRONTEND_LINKS = """
You can view these defects on [the code-review frontend]({frontend_url}) and on [Treeherder]({treeherder_url}).
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
            sorted(issues, key=lambda i: i.analyzer.name), lambda i: i.analyzer
        )

        def stats(analyzer, items):
            _items = list(items)
            paths = list({i.path for i in _items if i.is_publishable()})
            return {
                "analyzer": analyzer.display_name,
                "help": analyzer.build_help_message(paths),
                "total": len(_items),
                "publishable": sum([i.is_publishable() for i in _items]),
                "publishable_paths": paths,
            }

        return [stats(analyzer, items) for analyzer, items in groups]

    def build_comment(
        self,
        revision,
        issues,
        bug_report_url,
        frontend_url,
        patches=[],
        task_failures=[],
    ):
        """
        Build a Markdown comment about published issues
        """

        def pluralize(word, nb):
            assert isinstance(word, str)
            assert isinstance(nb, int)
            return "{} {}".format(nb, nb == 1 and word or word + "s")

        # List all the issues classes
        issue_classes = {issue.__class__ for issue in issues}

        # Calc stats for issues, grouped by class
        stats = self.calc_stats(issues)

        # Build parts depending on issues
        defects, analyzers = set(), set()
        for stat in stats:
            defects.add(
                " - {nb} found by {analyzer}".format(
                    analyzer=stat["analyzer"],
                    nb=pluralize("defect", stat["publishable"]),
                )
            )
            _help = stat.get("help")
            if _help is not None:
                analyzers.add(f" - {_help}")

        # Order both sets
        defects = sorted(defects)
        analyzers = sorted(analyzers)

        # Build top comment
        nb = len(issues)

        if nb > 0:
            comment = COMMENT_FAILURE.format(
                defects_total=pluralize("defect", nb), diff_id=revision.diff_id
            )
        else:
            comment = ""

        if not all(
            revision.contains(issue) for issue in issues if issue.is_publishable()
        ):
            comment += "(defects might be in the parent stack)\n"

        # Add defects
        if defects:
            comment += "\n".join(defects) + "\n"

        # Add build error
        nb_build_errors = sum(issue.is_build_error() for issue in issues)
        if nb_build_errors > 0:
            comment += "\nIMPORTANT: {} detected.\n".format(
                pluralize("build error", nb_build_errors)
            )

        if analyzers:
            comment += COMMENT_RUN_ANALYZERS.format(analyzers="\n".join(analyzers))

        for patch in patches:
            comment += COMMENT_DIFF_DOWNLOAD.format(
                analyzer=patch.analyzer.display_name, url=patch.url or patch.path
            )

        for task in task_failures:
            treeherder_url = treeherder.get_job_url(
                revision.repository_try_name,
                revision.mercurial_revision,
                task.id,
                task.run_id,
            )
            comment += COMMENT_TASK_FAILURE.format(name=task.name, url=treeherder_url)

        # Add coverage reporting details when a coverage issue is published
        if CoverageIssue in issue_classes:
            comment += COMMENT_COVERAGE

        assert comment != "", "Empty comment"

        comment += BUG_REPORT.format(bug_report_url=bug_report_url)

        if defects:
            treeherder_url = treeherder.get_job_url(
                revision.repository_try_name, revision.mercurial_revision
            )
            comment += FRONTEND_LINKS.format(
                frontend_url=frontend_url, treeherder_url=treeherder_url
            )

        return comment
