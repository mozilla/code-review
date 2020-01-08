# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from typing import List

import structlog
from libmozdata.phabricator import BuildState
from libmozdata.phabricator import PhabricatorAPI

from code_review_bot import Issue
from code_review_bot import Level
from code_review_bot import stats
from code_review_bot.report.base import Reporter
from code_review_bot.revisions import Revision
from code_review_bot.tasks.coverage import CoverageIssue

BUG_REPORT_URL = "https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__"  # noqa

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

        self.publish_build_errors = configuration.get("publish_build_errors", False)

    def setup_api(self, api):
        assert isinstance(api, PhabricatorAPI)
        self.api = api
        logger.info("Phabricator reporter enabled")

    def publish(self, issues, revision, task_failures):
        """
        Publish issues on Phabricator:
        * in patch issues use inline comments
        * outside errors are displayed as lint results
        * build errors are displayed as unit test results
        """
        if not isinstance(revision, Revision):
            logger.info(
                "Phabricator reporter only publishes Phabricator revisions. Skipping."
            )
            return None, None

        # Use only publishable issues and patches
        # and avoid publishing a patch from a de-activated analyzer
        issues = [
            issue
            for issue in issues
            if issue.is_publishable() and issue.analyzer not in self.analyzers_skipped
        ]
        patches = [
            patch
            for patch in revision.improvement_patches
            if patch.analyzer not in self.analyzers_skipped
        ]
        # List of issues without possible build errors
        issues_only = [issue for issue in issues if not issue.is_build_error()]
        build_errors = [issue for issue in issues if issue.is_build_error()]

        if issues_only or build_errors or task_failures:

            # Always publish comment summarizing issues
            self.publish_comment(revision, issues_only, patches, task_failures)

            # Publish all errors outside of the patch as lint issues
            lint_issues = [
                issue
                for issue in issues_only
                if not revision.contains(issue) and issue.level == Level.Error
            ]

            # Also publish build errors as Phabricator unit result
            unit_issues = build_errors if self.publish_build_errors else []

            # Publish on Harbormaster all at once
            self.publish_harbormaster(revision, lint_issues, unit_issues)
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
        if not lint_issues and not unit_issues:
            logger.info("No issues to publish as Phabricator lint or unit results")
            return

        self.api.update_build_target(
            revision.build_target_phid,
            state=BuildState.Work,
            lint=[issue.as_phabricator_lint() for issue in lint_issues],
            unit=[issue.as_phabricator_unitresult() for issue in unit_issues],
        )

    def publish_comment(self, revision, issues, patches, task_failures):
        """
        Publish issues through Phabricator comment
        """
        # Load existing comments for this revision
        existing_comments = self.api.list_comments(revision.phid)
        logger.info(
            "Found {} existing comments on review".format(len(existing_comments))
        )

        coverage_issues = [
            issue for issue in issues if isinstance(issue, CoverageIssue)
        ]
        non_coverage_issues = [
            issue for issue in issues if not isinstance(issue, CoverageIssue)
        ]
        patches_analyzers = set(p.analyzer for p in patches)

        # First publish inlines as drafts
        # * skipping coverage issues as they get a dedicated comment
        # * skipping issues reported in a patch
        # * skipping issues not in the current patch
        inlines = list(
            filter(
                None,
                [
                    self.comment_inline(revision, issue, existing_comments)
                    for issue in issues
                    if issue in non_coverage_issues
                    and issue.analyzer not in patches_analyzers
                    and revision.contains(issue)
                ],
            )
        )
        if not inlines and not patches and not coverage_issues and not task_failures:
            logger.info("No new comments found, skipping Phabricator publication")
            return
        logger.info("Added inline comments", ids=[i["id"] for i in inlines])

        # Then publish top comment
        if len(non_coverage_issues) or task_failures:
            self.api.comment(
                revision.id,
                self.build_comment(
                    revision=revision,
                    issues=non_coverage_issues,
                    patches=patches,
                    bug_report_url=BUG_REPORT_URL,
                    task_failures=task_failures,
                ),
            )

        # Then publish top coverage comment
        if len(coverage_issues):
            self.api.comment(
                revision.id,
                self.build_coverage_comment(
                    issues=coverage_issues, bug_report_url=BUG_REPORT_URL
                ),
            )

        stats.add_metric("report.phabricator.issues", len(inlines))
        stats.add_metric("report.phabricator")
        logger.info("Published phabricator comment")

    def comment_inline(self, revision, issue, existing_comments=[]):
        """
        Post an inline comment on a diff
        """
        assert isinstance(revision, Revision)
        assert isinstance(issue, Issue)

        # Enforce path validation or Phabricator will crash here
        if not revision.has_file(issue.path):
            logger.warn(
                "Will not publish inline comment on invalid path {}: {}".format(
                    issue.path, issue
                )
            )
            return

        # Check if comment is already posted
        comment = {
            "diffID": revision.diff_id,
            "filePath": issue.path,
            "lineNumber": issue.line
            if issue.line is not None
            else 1,  # support full file
            "lineLength": issue.nb_lines - 1,
            "content": issue.as_text(),
        }
        if comment in existing_comments:
            logger.info(
                "Skipping existing comment",
                text=comment["content"],
                filename=comment["filePath"],
                line=comment["lineNumber"],
            )
            return

        inline = self.api.request(
            "differential.createinline",
            # This displays on the new file (right side)
            # Python boolean is not recognized by Conduit :/
            isNewFile=1,
            # Use comment data
            **comment
        )
        return inline
