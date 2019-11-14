# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import structlog
from libmozdata.phabricator import BuildState
from libmozdata.phabricator import PhabricatorAPI

from code_review_bot import Issue
from code_review_bot import stats
from code_review_bot.report.base import Reporter
from code_review_bot.revisions import Revision
from code_review_bot.tasks.coverage import CoverageIssue

MODE_COMMENT = "comment"
MODE_HARBORMASTER = "harbormaster"
BUG_REPORT_URL = "https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__"  # noqa

logger = structlog.get_logger(__name__)


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

        self.mode = configuration.get("mode", MODE_COMMENT)
        self.publish_build_errors = configuration.get("publish_build_errors", False)
        assert self.mode in (MODE_COMMENT, MODE_HARBORMASTER), "Invalid mode"
        logger.info(
            "Will publish using", mode=self.mode, build_errors=self.publish_build_errors
        )

    def setup_api(self, api):
        assert isinstance(api, PhabricatorAPI)
        self.api = api
        logger.info("Phabricator reporter enabled")

    def publish(self, issues, revision):
        """
        Publish inline comments for each issues
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

        if issues_only or build_errors:
            if self.mode == MODE_COMMENT:
                self.publish_comment(revision, issues_only, patches)
            elif self.mode == MODE_HARBORMASTER:
                self.publish_harbormaster(revision, issues_only)
            else:
                raise Exception("Unsupported mode {}".format(self.mode))
            # Also publish build issues
            if self.publish_build_errors:
                self.publish_harbormaster_build_errors(revision, build_errors)
        else:
            logger.info("No issues to publish on phabricator")

        return issues, patches

    def publish_harbormaster_build_errors(self, revision, issues):
        """
        Publish build errors through Phabricator UnitResult
        """
        if not issues:
            logger.info("No build errors encountered")
            return
        self.api.update_build_target(
            revision.build_target_phid,
            BuildState.Fail,
            unit=[issue.as_phabricator_unitresult() for issue in issues],
        )

    def publish_comment(self, revision, issues, patches):
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
        inlines = list(
            filter(
                None,
                [
                    self.comment_inline(revision, issue, existing_comments)
                    for issue in issues
                    if issue in non_coverage_issues
                    and issue.analyzer not in patches_analyzers
                ],
            )
        )
        if not inlines and not patches and not coverage_issues:
            logger.info("No new comments found, skipping Phabricator publication")
            return
        logger.info("Added inline comments", ids=[i["id"] for i in inlines])

        # Then publish top comment
        if len(non_coverage_issues):
            self.api.comment(
                revision.id,
                self.build_comment(
                    revision=revision,
                    issues=non_coverage_issues,
                    patches=patches,
                    bug_report_url=BUG_REPORT_URL,
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

    def publish_harbormaster(self, revision, issues):
        """
        Publish issues through HarborMaster
        """
        revision.update_status(
            state=BuildState.Work,
            lint_issues=[issue.as_phabricator_lint() for issue in issues],
        )

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
