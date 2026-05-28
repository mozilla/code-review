# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import structlog

from code_review_bot.report.base import Reporter
from code_review_bot.revisions import GithubRevision
from code_review_bot.sources.github import GithubClient, ReviewEvent

logger = structlog.get_logger(__name__)


class GithubReporter(Reporter):
    # Auth to Github using a configuration (from Taskcluster secret)

    def __init__(self, configuration={}, *args, **kwargs):
        for key in ("client_id", "private_key_pem", "installation_id"):
            if not configuration.get(key):
                raise Exception(f"Missing github reporter configuration key {key}")

        # Setup github App secret from the configuration
        self.github_client = GithubClient(
            client_id=configuration["client_id"],
            private_key=configuration["private_key_pem"],
            installation_id=configuration["installation_id"],
        )

        self.analyzers_skipped = configuration.get("analyzers_skipped", [])
        assert isinstance(
            self.analyzers_skipped, list
        ), "analyzers_skipped must be a list"

    def publish(self, issues, revision, task_failures, notices, reviewers):
        """
        Publish issues on a Github pull request.
        """
        if not isinstance(revision, GithubRevision):
            logger.info(
                "Skipping github reporting, only available for Github revisions"
            )
            return

        if reviewers:
            logger.warn(
                f"These reviewer groups should be assigned, but it's not yet possible on Github: {', '.join(reviewers)}"
            )

        # Avoid publishing a patch from a de-activated analyzer
        publishable_issues = [
            issue
            for issue in issues
            if issue.is_publishable()
            and issue.analyzer.name not in self.analyzers_skipped
        ]
        # Issues that are not in patch cannot be published directly through a Github review
        inside_patch_issues = [issue for issue in publishable_issues if issue.in_patch]
        outside_patch_issues = [
            issue for issue in publishable_issues if not issue.in_patch
        ]

        # Remove any earlier review to get a clean state
        nb_dismissed = self.github_client.cleanup_pr(revision)

        if publishable_issues:
            if outside_patch_issues:
                # Directly publish a comment to the PR for issues outside of the patch
                message = [
                    f"Code review bot detected {len(outside_patch_issues)} issue{'s' if len(issues) > 1 else ''} "
                    "outside of the patch:"
                ]
                for issue in outside_patch_issues:
                    message.append(f"* `{issue.path}:{issue.line}` {issue.as_text()}")
                self.github_client.publish_comment(
                    revision=revision, message="\n".join(message)
                )

            # Publish a review summarizing detected, unresolved and closed issues
            self.github_client.publish_review(
                issues=inside_patch_issues,
                revision=revision,
                message=(
                    f"{len(publishable_issues)} issue{'s' if len(publishable_issues) > 1 else ''} "
                    f"{'have' if len(publishable_issues) > 1 else 'has'} "
                    "been found in this revision"
                ),
                event=ReviewEvent.RequestChanges,
            )
        else:
            # Publish a comment, mentioning if previous issues were cleared up
            logger.info(
                "No publishable issue, posting a standalone comment",
                nb_dismissed=nb_dismissed,
            )
            if nb_dismissed > 0:
                message = "Previous issues have been fixed. This pull request is :ok:"
            else:
                message = "No new issues detected. This pull request is :ok:"

            self.github_client.publish_comment(
                revision=revision,
                message=message,
            )
