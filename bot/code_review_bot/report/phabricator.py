# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from typing import List

import structlog
from libmozdata.phabricator import BuildState
from libmozdata.phabricator import PhabricatorAPI

from code_review_bot import Issue
from code_review_bot import stats
from code_review_bot.report.base import Reporter

BUG_REPORT_URL = "https://bugzilla.mozilla.org/enter_bug.cgi?product=Firefox+Build+System&component=Source+Code+Analysis&short_desc=[Automated+review]+UPDATE&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__"

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

    def setup_api(self, api):
        assert isinstance(api, PhabricatorAPI)
        self.api = api
        logger.info("Phabricator reporter enabled")

    def publish(self, issues, revision, task_failures, links):
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

        if issues or task_failures or links:

            if issues:
                # Publish on Harbormaster all at once
                # * All non coverage publishable issues as lint issues
                # * All build errors as unit test results
                self.publish_harbormaster(revision, issues)

            if issues or patches or task_failures or links:
                # Publish comment summarizing issues
                self.publish_summary(revision, issues, patches, task_failures, links)

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

    def publish_summary(self, revision, issues, patches, task_failures, links=None):
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
                frontend_url=self.frontend_diff_url.format(diff_id=revision.diff_id),
                task_failures=task_failures,
                links=links,
            ),
        )
        logger.info("Published phabricator summary")
