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

        self.github_client = GithubClient.from_configuration(configuration)

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
        if not self.github_client:
            logger.error(
                "Github API client is not initialized, skipping Github reporting"
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

        # Remove any earlier review to get a clean state
        nb_dismissed = self.github_client.cleanup_pr(revision)

        if publishable_issues:
            # Publish a review summarizing detected, unresolved and closed issues
            self.github_client.publish_review(
                issues=publishable_issues,
                revision=revision,
                message=f"{len(publishable_issues)} issues have been found in this revision",
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
