# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from code_review_bot.report.base import Reporter
from code_review_bot.sources.github import GithubClient


class GithubReporter(Reporter):
    # Auth to Github using a configuration (from Taskcluster secret)

    def __init__(self, configuration={}, *args, **kwargs):
        if kwargs.get("api") is not None:
            api_url = kwargs["api"]
        else:
            api_url = "https://api.github.com/"

        # Setup github App secret from the configuration
        self.github_client = GithubClient(
            api_url=api_url,
            client_id=configuration.get("app_client_id"),
            pem_file_path=configuration.get("app_pem_file"),
        )

        self.analyzers_skipped = configuration.get("analyzers_skipped", [])
        assert isinstance(
            self.analyzers_skipped, list
        ), "analyzers_skipped must be a list"

    def publish(self, issues, revision, task_failures, notices, reviewers):
        """
        Publish issues on a Github pull request.
        """
        raise NotImplementedError

    @property
    def github_jwt_token(self):
        # Use the GitHub App's private key to create a JWT (JSON Web Token).
        # Exchange the JWT for an installation access token via the GitHub API.
        raise NotImplementedError

    def comment(self, *, owner, repo, issue_number, message):
        self.github_client.make_request(
            "post", f"repos/{owner}/{repo}/issues/{issue_number}/comments", json=message
        )
