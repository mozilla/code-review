# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import structlog

from code_review_bot.report.base import Reporter
from code_review_bot.sources.github import GithubClient

logger = structlog.get_logger(__name__)


class GithubReporter(Reporter):
    # Auth to Github using a configuration (from Taskcluster secret)

    def __init__(self, configuration={}, *args, **kwargs):
        # Setup github App secret from the configuration
        self.github_client = GithubClient(
            client_id=configuration.get("app_client_id"),
            pem_key_path=configuration.get("app_pem_file"),
            installation_id=configuration.get("app_installation_id"),
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
        if not publishable_issues:
            logger.info("No publishable issue, nothing to do")
            return

        message = f"{len(issues)} issues have been found in this revision"

        # Publish a review summarizing detected, unresolved and closed issues
        self.github_client.publish_review(
            issues=issues, revision=revision, message=message
        )
