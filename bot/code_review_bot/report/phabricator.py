# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from typing import List
from urllib.parse import urljoin

import structlog
from libmozdata.phabricator import BuildState
from libmozdata.phabricator import PhabricatorAPI

from code_review_bot import Issue
from code_review_bot import stats
from code_review_bot.report.base import Reporter
from code_review_bot.tasks.clang_tidy_external import ExternalTidyIssue
from code_review_bot.tasks.coverage import CoverageIssue
from code_review_tools import treeherder

BUG_REPORT_URL = "https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+THIS+IS+A+PLACEHOLDER&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__"

COMMENT_FAILURE = """
Code analysis found {defects_total} in the diff [{diff_id}]({phabricator_diff_url}):
"""

COMMENT_WARNINGS = """
WARNING: Found {nb_warnings} (warning level) that can be dismissed.
"""

COMMENT_ERRORS = """
IMPORTANT: Found {nb_errors} (error level) that must be fixed before landing.
"""

COMMENT_RUN_ANALYZERS = """
You can run this analysis locally with:
{analyzers}
"""

COMMENT_COVERAGE = """
In our previous code coverage analysis run, we found some files which had no coverage and are being modified in this patch:
Should they have tests, or are they dead code?

 - You can file a bug blocking [Bug 1415824](https://bugzilla.mozilla.org/show_bug.cgi?id=1415824) for untested files that should be **tested**.
 - You can file a bug blocking [Bug 1415819](https://bugzilla.mozilla.org/show_bug.cgi?id=1415819) for untested files that should be **removed**.
"""

BUG_REPORT = """
---
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
You can view these defects in the Diff Detail section of [Phabricator diff {diff_id}]({phabricator_diff_url}).
"""


logger = structlog.get_logger(__name__)

Issues = List[Issue]


class PhabricatorReporter(Reporter):
    """
    API connector to report on Phabricator
    """

    def __init__(self, configuration={}, *args, **kwargs):
        if kwargs.get("api") is not None:
            self.setup_api(kwargs["api"])

        self.analyzers_skipped = configuration.get("analyzers_skipped", [])
        assert isinstance(
            self.analyzers_skipped, list
        ), "analyzers_skipped must be a list"

        self.frontend_diff_url = configuration.get(
            "frontend_diff_url", "https://code-review.moz.tools/#/diff/{diff_id}"
        )
        self.phabricator_diff_url = urljoin(
            configuration.get(
                "phabricator_base_url", "https://phabricator.services.mozilla.com"
            ),
            "differential/diff/{diff_id}/",
        )

    def setup_api(self, api):
        assert isinstance(api, PhabricatorAPI)
        self.api = api
        logger.info("Phabricator reporter enabled")

    def publish(self, issues, revision, task_failures, notices):
        """
        Publish issues on Phabricator:
        * publishable issues use lint results
        * build errors are displayed as unit test results
        """

        # Use only publishable issues and patches
        # and avoid publishing a patch from a de-activated analyzer
        issues = [
            issue
            for issue in issues
            if issue.is_publishable()
            and issue.analyzer.name not in self.analyzers_skipped
        ]
        patches = [
            patch
            for patch in revision.improvement_patches
            if patch.analyzer.name not in self.analyzers_skipped
        ]

        if issues or task_failures or notices:

            if issues:
                # Publish on Harbormaster all at once
                # * All non coverage publishable issues as lint issues
                # * All build errors as unit test results
                self.publish_harbormaster(revision, issues)

            all_diffs = self.api.search_diffs(revision_phid=revision.phid)
            newer_diffs = [diff for diff in all_diffs if diff["id"] > revision.diff_id]
            # If a newer diff already exists we don't want to publish a comment on Phabricator
            if newer_diffs:
                logger.warning(
                    "A newer diff exists on this patch, skipping the comment publication"
                )
            else:
                if issues or patches or task_failures or notices:
                    # Publish comment summarizing issues
                    self.publish_summary(
                        revision, issues, patches, task_failures, notices
                    )

                # Publish statistics
                stats.add_metric("report.phabricator.issues", len(issues))
                stats.add_metric("report.phabricator")
        else:
            logger.info("No issues to publish on phabricator")

        return issues, patches

    def publish_harbormaster(
        self, revision, lint_issues: Issues = [], unit_issues: Issues = []
    ):
        """
        Publish issues through HarborMaster
        either as lint results or unit tests results
        """
        assert lint_issues or unit_issues, "No issues to publish"

        self.api.update_build_target(
            revision.build_target_phid,
            state=BuildState.Work,
            lint=[issue.as_phabricator_lint() for issue in lint_issues],
            unit=[issue.as_phabricator_unitresult() for issue in unit_issues],
        )
        logger.info(
            "Updated Harbormaster build state with issues",
            nb_lint=len(lint_issues),
            nb_unit=len(unit_issues),
        )

    def publish_summary(self, revision, issues, patches, task_failures, notices):
        """
        Summarize publishable issues through Phabricator comment
        """
        self.api.comment(
            revision.id,
            self.build_comment(
                revision=revision,
                issues=issues,
                patches=patches,
                bug_report_url=BUG_REPORT_URL,
                task_failures=task_failures,
                notices=notices,
            ),
        )
        logger.info("Published phabricator summary")

    def build_comment(
        self,
        revision,
        issues,
        bug_report_url,
        notices,
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
        total_warnings = 0
        total_errors = 0
        for stat in stats:
            defect_nb = []
            if stat["nb_build_errors"] > 0:
                defect_nb.append(pluralize("build error", stat["nb_build_errors"]))
            if stat["nb_defects"] > 0:
                defect_nb.append(pluralize("defect", stat["nb_defects"]))

            defects.add(
                " - {nb} found by {analyzer}".format(
                    analyzer=stat["analyzer"], nb=" and ".join(defect_nb)
                )
            )
            _help = stat.get("help")
            if _help is not None:
                analyzers.add(f" - {_help}")

            total_warnings += stat["nb_warnings"]
            total_errors += stat["nb_errors"]

        # Order both sets
        defects = sorted(defects)
        analyzers = sorted(analyzers)

        # Comment with an absolute link to the revision diff in Phabricator
        # Relative links are not supported in comment and non readable in related emails
        phabricator_diff_url = self.phabricator_diff_url.format(
            diff_id=revision.diff_id
        )

        # Build top comment
        nb = len(issues)

        if nb > 0:
            comment = COMMENT_FAILURE.format(
                defects_total=pluralize("defect", nb),
                diff_id=revision.diff_id,
                phabricator_diff_url=phabricator_diff_url,
            )
        else:
            comment = ""

        # Add defects
        if defects:
            comment += "\n".join(defects) + "\n"

        # Add colored warning section
        if total_warnings:
            comment += COMMENT_WARNINGS.format(
                nb_warnings=pluralize("issue", total_warnings)
            )

        # Add colored error section
        if total_errors:
            comment += COMMENT_ERRORS.format(nb_errors=pluralize("issue", total_errors))

        if analyzers:
            comment += COMMENT_RUN_ANALYZERS.format(analyzers="\n".join(analyzers))

        for tidy_external_issue in filter(
            lambda i: isinstance(i, ExternalTidyIssue), issues
        ):
            comment += tidy_external_issue.as_markdown_for_phab()

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

        if notices:
            # The '---' creates a horizontal rule in Phabricator's markdown
            comment += "\n---\n".join(notices)

        assert comment != "", "Empty comment"

        comment += BUG_REPORT.format(bug_report_url=bug_report_url)

        if defects:
            comment += FRONTEND_LINKS.format(
                diff_id=revision.diff_id,
                phabricator_diff_url=phabricator_diff_url,
            )

        return comment
