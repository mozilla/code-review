#!/usr/bin/env python3

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from github import Auth, GithubIntegration


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

    def comment(
        self,
        *,
        revision,  # GithubRevision
        issue,
    ):
        repo = self.api.get_repo(revision.repository)
        pull_request = repo.get_pull(revision.pull_id)
        pull_request.create_comment(
            commit=revision.commit,
            path=issue.path,
            position=issue.line,
            body=issue.message,
        )
