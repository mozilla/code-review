#!/usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import enum
from functools import lru_cache

import structlog
from github import Auth, GithubIntegration
from github.PullRequest import ReviewComment

from code_review_bot import Issue
from code_review_bot.revisions import GithubRevision

logger = structlog.get_logger(__name__)


# Github does not provide an exact limit for the body content on its API.
# We prefer using a safe interval here, based on https://github.com/dead-claudia/github-limits#issue-comments
GITHUB_COMMENT_LIMIT = 65536


class ReviewEvent(enum.Enum):
    """
    Review action you want to perform.
    https://docs.github.com/en/rest/pulls/reviews?apiVersion=2022-11-28#create-a-review-for-a-pull-request--parameters
    """

    Pending = "PENDING"
    Approved = "APPROVE"
    RequestChanges = "REQUEST_CHANGES"
    Comment = "COMMENT"


class GithubClient:
    def __init__(self, client_id: str, private_key: str, installation_id: str):
        self.client_id = client_id

        # Setup auth
        self.auth = Auth.AppAuth(self.client_id, private_key)
        self.github_integration = GithubIntegration(auth=self.auth)

        installations = self.github_integration.get_installations()
        self.installation = next(
            (i for i in installations if i.id == installation_id), None
        )
        if not self.installation:
            raise ValueError(
                f"Installation ID is not available. Available installations are {list(installations)}"
            )
        # setup API
        self.api = self.installation.get_github_for_installation()

        self.review_comments = []

    @classmethod
    def from_configuration(cls, configuration: dict):
        """Setup github App secrets from the configuration"""
        if not all(
            configuration.get(key)
            for key in ("client_id", "private_key_pem", "installation_id")
        ):
            logger.warning(
                "Missing github reporter configuration key. Github API client was not initialized"
            )
            return
        return cls(
            client_id=configuration["client_id"],
            private_key=configuration["private_key_pem"],
            installation_id=configuration["installation_id"],
        )

    @lru_cache
    def get_pull_request(self, revision: GithubRevision):
        repo = self.api.get_repo(revision.repo_name)
        return repo.get_pull(revision.pull_number)

    def _build_review_comment(self, issue):
        message = issue.message
        if len(message) > GITHUB_COMMENT_LIMIT:
            message = message[: GITHUB_COMMENT_LIMIT - 1] + "…"

        return ReviewComment(
            path=issue.path,
            line=issue.line,
            body=message,
        )

    def publish_comment(
        self,
        revision: GithubRevision,
        message: str | None = None,
    ):
        """
        Publish a comment on a pull request
        """
        assert isinstance(revision, GithubRevision), "Only for github revisions"

        pull_request = self.get_pull_request(revision)

        if len(message) > GITHUB_COMMENT_LIMIT:
            message = message[: GITHUB_COMMENT_LIMIT - 1] + "…"

        pull_request.create_issue_comment(body=message)

    def publish_review(
        self,
        issues: list[Issue],
        revision: GithubRevision,
        event: ReviewEvent,
        message: str | None = None,
    ):
        """
        Publish a review from a list of publishable issues, requesting changes to the author.
        """
        assert isinstance(revision, GithubRevision), "Only for github revisions"

        repo = self.api.get_repo(revision.repo_name)
        pull_request = repo.get_pull(revision.pull_number)

        attrs = {}
        if message is None:
            assert (
                event == ReviewEvent.Approved
            ), "Body can be left null only when approving a pull request"
        else:
            attrs["body"] = message

        pull_request.create_review(
            commit=repo.get_commit(revision.head_changeset),
            comments=[self._build_review_comment(issue) for issue in issues],
            # https://docs.github.com/en/rest/pulls/reviews?apiVersion=2022-11-28#create-a-review-for-a-pull-request
            event=event.value,
            **attrs,
        )

    def cleanup_pr(self, revision: GithubRevision):
        """
        Dismiss previous reviews from the bot
        """
        assert isinstance(revision, GithubRevision), "Only for github revisions"

        pr = self.get_pull_request(revision)

        nb = 0
        for review in pr.get_reviews():
            # Only process our own reviews
            if review.user.login != "mozilla-code-review[bot]":
                continue

            # Only process active reviews
            if review.state == "DISMISSED":
                continue

            try:
                review.dismiss("This review is now deprecated.")
                logger.info(
                    "Dismissed previous Github review from the bot",
                    review=review.id,
                    submitted=review.submitted_at,
                )
                nb += 1
            except Exception as e:
                logger.warn(
                    "Failed to dismiss previous Github review from the bot",
                    review=review.id,
                    submitted=review.submitted_at,
                    error=e,
                )
                raise  # trashme

        return nb
