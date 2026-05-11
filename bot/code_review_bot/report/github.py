# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import structlog

from code_review_bot.report.base import Reporter
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
        if reviewers:
            raise NotImplementedError
        # Avoid publishing a patch from a de-activated analyzer
        publishable_issues = [
            issue
            for issue in issues
            if issue.is_publishable()
            and issue.analyzer.name not in self.analyzers_skipped
        ]

        if publishable_issues:
            # Publish a review summarizing detected, unresolved and closed issues
            message = f"{len(issues)} issues have been found in this revision"
            event = ReviewEvent.RequestChanges
        else:
            # Simply approve the pull request
            logger.info("No publishable issue, approving the pull request")
            message = None
            event = ReviewEvent.Approved

        self.github_client.publish_review(
            issues=publishable_issues,
            revision=revision,
            message=message,
            event=event,
        )
