# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import defaultdict
from typing import List
from urllib.parse import urljoin

import structlog
from libmozdata.phabricator import BuildState, PhabricatorAPI

from code_review_bot import Issue, Level, stats
from code_review_bot.backend import BackendAPI
from code_review_bot.report.base import Reporter
from code_review_bot.tasks.clang_tidy_external import ExternalTidyIssue
from code_review_bot.tasks.coverage import CoverageIssue
from code_review_tools import treeherder

BUG_REPORT_URL = "https://bugzilla.mozilla.org/enter_bug.cgi?product=Developer+Infrastructure&component=Source+Code+Analysis&short_desc=[Automated+review]+THIS+IS+A+PLACEHOLDER&comment=**Phabricator+URL:**+https://phabricator.services.mozilla.com/...&format=__default__"

COMMENT_FAILURE = """
Code analysis found {defects_total} in diff [{diff_id}]({phabricator_diff_url}):
"""

COMMENT_WARNINGS = """
WARNING: Found {nb_warnings} (warning level) that can be dismissed.
"""

COMMENT_ERRORS = """
IMPORTANT: Found {nb_errors} (error level) that must be fixed before landing.
"""

COMMENT_DIFF_FOLLOWUP = """compared to the previous diff [{diff_id}]({phabricator_diff_url}).
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

# Use two line breaks to force '---' to be rendered as a horizontal rule in Phabricator's markdown
BUG_REPORT = """
If you see a problem in this automated review, [please report it here]({bug_report_url}).
"""

COMMENT_DIFF_DOWNLOAD = """
For your convenience, [here is a patch]({url}) that fixes all the {analyzer} defects (use it in your repository with `hg import` or `git apply -p0`).
"""

COMMENT_TASK_FAILURE = """
The analysis task [{name}]({url}) failed, but we could not detect any defect.
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
        # Setup Code Review backend API client
        self.backend_api = BackendAPI()

    def setup_api(self, api):
        assert isinstance(api, PhabricatorAPI)
        self.api = api
        logger.info("Phabricator reporter enabled")

    @staticmethod
    def pluralize(word, nb):
        """
        Simple helper to pluralize a noun depending of the number of elements
        """
        assert isinstance(word, str)
        assert isinstance(nb, int)
        return "{} {}".format(nb, nb == 1 and word or word + "s")

    def compare_issues(self, former_diff_id, issues):
        """
        Compare new issues depending on their evolution from the
        previous diff on the same revision.
        Returns a tuple containing lists of:
          * Unresolved issues, that are present on both diffs
          * Closed issues, that were present in the previous diff and are now gone
        """
        if not self.backend_api.enabled:
            logger.warning(
                "Backend API must be enabled to compare issues with previous diff {former_diff_id}."
            )
            return [], []

        # If this is the first diff, there's no need to compare issues with a
        # previous diff since there is no previous diff.
        if former_diff_id is None:
            return [], []

        # Retrieve issues related to the previous diff
        try:
            previous_issues = self.backend_api.list_diff_issues(former_diff_id)
        except Exception as e:
            logger.warning(
                f"An error occurred listing issues on previous diff {former_diff_id}: {e}. "
                "Each issue will be considered as a new case."
            )
            previous_issues = []

        # Multiple issues may share a similar hash in case they were
        # produced by the same linter on the same lines
        indexed_issues = defaultdict(list)
        for issue in previous_issues:
            indexed_issues[issue["hash"]].append(issue)

        # Compare current issues with the previous ones based on the hash
        unresolved = [
            issue.on_backend["hash"]
            for issue in issues
            if issue.on_backend and issue.on_backend["hash"] in indexed_issues
        ]

        # All previous issues that are not unresolved are closed
        closed = [issue for issue in previous_issues if issue["hash"] not in unresolved]

        return unresolved, closed

    def publish(self, issues, revision, task_failures, notices, reviewers):
        """
        Publish issues on Phabricator:
        * publishable issues use lint results
        * build errors are displayed as unit test results
        """

        # Add extra reviewers groups to the revision
        if reviewers:
            phids = []
            for reviewers_group in reviewers:
                data = self.api.search_projects(slugs=[reviewers_group])
                if not data or "phid" not in data[0]:
                    logger.warning(
                        f'Unable to find the PHID of the reviewers group identified by the slug "{reviewers_group}"'
                    )
                    continue

                phids.append(data[0]["phid"])

            if phids:
                self.api.edit_revision(
                    revision.phabricator_id,
                    [
                        {
                            "type": "reviewers.add",
                            "value": phids,
                        }
                    ],
                )

        # Use only new and publishable issues and patches
        # Avoid publishing a patch from a de-activated analyzer
        publishable_issues = [
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

        if publishable_issues:
            # Publish detected patch's issues on Harbormaster, all at once, as lint issues
            self.publish_harbormaster(revision, publishable_issues)

        # Retrieve all diffs for the current revision
        rev_diffs = self.api.search_diffs(revision_phid=revision.phabricator_phid)

        if any(diff["id"] > revision.diff_id for diff in rev_diffs):
            logger.warning(
                "A newer diff exists on this patch, skipping the comment publication"
            )
            return publishable_issues, patches

        # Compare issues that are not known on the repository to a previous diff
        older_diff_ids = [
            diff["id"] for diff in rev_diffs if diff["id"] < revision.diff_id
        ]
        former_diff_id = sorted(older_diff_ids)[-1] if older_diff_ids else None
        unresolved_issues, closed_issues = self.compare_issues(
            former_diff_id, publishable_issues
        )

        if (
            len(unresolved_issues) == len(publishable_issues)
            and not closed_issues
            and not task_failures
            and not notices
        ):
            # Nothing changed, no issue have been opened or closed
            logger.info(
                "No new issues nor failures/notices were detected. "
                "Skipping comment publication (some issues are unresolved)",
                unresolved_count=len(unresolved_issues),
            )
            return publishable_issues, patches

        # Publish comment summarizing detected, unresolved and closed issues
        self.publish_summary(
            revision,
            publishable_issues,
            patches,
            task_failures,
            notices,
            former_diff_id=former_diff_id,
            unresolved_count=len(unresolved_issues),
            closed_count=len(closed_issues),
        )

        # Publish statistics
        stats.add_metric("report.phabricator.issues", len(issues))
        stats.add_metric("report.phabricator")

        return publishable_issues, patches

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

    def publish_summary(
        self,
        revision,
        issues,
        patches,
        task_failures,
        notices,
        former_diff_id,
        unresolved_count,
        closed_count,
    ):
        """
        Summarize publishable issues through Phabricator comment
        """
        self.api.comment(
            revision.phabricator_id,
            self.build_comment(
                revision=revision,
                issues=issues,
                patches=patches,
                bug_report_url=BUG_REPORT_URL,
                task_failures=task_failures,
                notices=notices,
                former_diff_id=former_diff_id,
                unresolved=unresolved_count,
                closed=closed_count,
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
        former_diff_id=None,
        unresolved=0,
        closed=0,
    ):
        """
        Build a Markdown comment about published issues
        """
        comment = ""

        # Comment with an absolute link to the revision diff in Phabricator
        # Relative links are not supported in comment and non readable in related emails
        phabricator_diff_url = self.phabricator_diff_url.format(
            diff_id=revision.diff_id
        )

        # Build main comment for issues inside the patch
        if (nb := len(issues)) > 0:
            comment = COMMENT_FAILURE.format(
                defects_total=self.pluralize("defect", nb),
                diff_id=revision.diff_id,
                phabricator_diff_url=phabricator_diff_url,
            )

        # Calc stats for issues inside the patch, grouped by class and sorted by number of issues
        defects = []
        stats = self.calc_stats(issues)
        for stat in sorted(stats, key=lambda x: (x["total"], x["analyzer"])):
            defect_nb = []
            if stat["nb_build_errors"] > 0:
                defect_nb.append(self.pluralize("build error", stat["nb_build_errors"]))
            if stat["nb_defects"] > 0:
                defect_nb.append(self.pluralize("defect", stat["nb_defects"]))

            defects.append(
                " - {nb} found by {analyzer}".format(
                    analyzer=stat["analyzer"], nb=" and ".join(defect_nb)
                )
            )
        if defects:
            comment += "\n".join(defects) + "\n"

        # In case of a new diff, display the number of resolved or closed issues
        if unresolved or closed:
            followup_comment = ""
            if unresolved:
                followup_comment += (
                    self.pluralize("defect", unresolved) + " unresolved "
                )
                if closed:
                    followup_comment += "and "
            if closed:
                followup_comment += self.pluralize("defect", closed) + " closed "
            followup_comment += COMMENT_DIFF_FOLLOWUP.format(
                phabricator_diff_url=self.phabricator_diff_url.format(
                    diff_id=former_diff_id
                ),
                diff_id=former_diff_id,
            )
            comment += followup_comment

        # Add colored warning section
        total_warnings = sum(1 for i in issues if i.level == Level.Warning)
        if total_warnings:
            comment += COMMENT_WARNINGS.format(
                nb_warnings=self.pluralize("defect", total_warnings)
            )

        # Add colored error section
        total_errors = sum(1 for i in issues if i.level == Level.Error)
        if total_errors:
            comment += COMMENT_ERRORS.format(
                nb_errors=self.pluralize("defect", total_errors)
            )

        # Build analyzers help comment for all issues
        analyzers = set()
        for stat in stats:
            _help = stat.get("help")
            if _help is not None:
                analyzers.add(f" - {_help}")
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
                revision.head_changeset,
                task.id,
                task.run_id,
            )
            comment += COMMENT_TASK_FAILURE.format(name=task.name, url=treeherder_url)

        # Add coverage reporting details when a coverage issue is published
        issue_classes = {issue.__class__ for issue in issues}
        if CoverageIssue in issue_classes:
            comment += COMMENT_COVERAGE

        if notices:
            # Use two line breaks to force '---' to be rendered as a horizontal rule in Phabricator's markdown
            comment += "\n\n---\n".join(notices)

        assert comment != "", "Empty comment"

        # Display more information in the footer section
        comment += "\n\n---\n"

        comment += BUG_REPORT.format(bug_report_url=bug_report_url)

        if defects:
            comment += FRONTEND_LINKS.format(
                diff_id=revision.diff_id,
                phabricator_diff_url=phabricator_diff_url,
            )

        return comment
