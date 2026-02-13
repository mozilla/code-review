#!/usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from github import Auth, GithubIntegration
from github.PullRequest import ReviewComment

from code_review_bot import Issue
from code_review_bot.revisions import GithubRevision


class GithubClient:
    def __init__(self, client_id: str, pem_key_path: str, installation_id: str):
        self.client_id = client_id
        with open(pem_key_path) as f:
            private_key = f.read()

        # Setup auth
        self.auth = Auth.AppAuth(self.client_id, private_key)
        self.github_integration = GithubIntegration(auth=self.auth)

        installations = self.github_integration.get_installations()
        self.installation = next(
            (i for i in installations if str(i.id) == installation_id), None
        )
        if not self.installation:
            raise ValueError(
                f"Installation ID is not available. Available installations are {list(installations)}"
            )
        # setup API
        self.api = self.installation.get_github_for_installation()

        self.review_comments = []

    def _build_review_comment(self, issue):
        return ReviewComment(
            path=issue.path,
            position=issue.line,
            body=issue.message,
        )

    def publish_review(
        self, issues: list[Issue], revision: GithubRevision, message: str
    ):
        """
        Publish a review from a list of publishable issues, requesting changes to the author.
        """
        repo = self.api.get_repo(revision.repo_name)
        pull_request = repo.get_pull(revision.pull_number)
        pull_request.create_review(
            commit=repo.get_commit(revision.pull_head_sha),
            body=message,
            comments=[self._build_review_comment(issue) for issue in issues],
            # https://docs.github.com/en/rest/pulls/reviews?apiVersion=2022-11-28#create-a-review-for-a-pull-request
            event="REQUEST_CHANGES",
        )
