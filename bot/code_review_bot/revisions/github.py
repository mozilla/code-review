# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from functools import cached_property
from urllib.parse import urlparse

import requests
import structlog

from code_review_bot import taskcluster
from code_review_bot.git import build_repo_slug
from code_review_bot.revisions import Revision

logger = structlog.get_logger(__name__)


class GithubRevision(Revision):
    """
    A revision from a github pull-request
    """

    def __init__(
        self,
        base_repository,
        base_changeset,
        head_repository,
        head_changeset,
        pull_number,
    ):
        super().__init__()

        self.base_repository = base_repository
        self.base_changeset = base_changeset
        self.head_repository = head_repository
        self.head_changeset = head_changeset
        self.pull_number = pull_number

        # Load the patch from Github
        self.patch = self.load_patch()

    def __str__(self):
        return f"Github pull request {self.base_repository} #{self.pull_number} ({self.head_changeset[:8]})"

    def __repr__(self):
        return f"GithubRevision base_repo={self.base_repository} head_repo={self.head_repository} pull_number={self.pull_number} head={self.head_changeset}"

    @property
    def repo_name(self):
        """
        Extract the name of the repository from its URL
        """
        return urlparse(self.base_repository).path.strip("/")

    @property
    def repository_slug(self):
        """
        Generate a slug from the Github repository.
        """
        return build_repo_slug(self.base_repository)

    def load_patch(self):
        """
        Load the patch content for the current pull request HEAD
        """
        # TODO: use specific sha
        url = f"{self.base_repository}/pull/{self.pull_number}.diff"
        logger.info("Loading github patch", url=url)
        resp = requests.get(url, allow_redirects=True)
        resp.raise_for_status()
        return resp.content.decode()

    def as_dict(self):
        return {
            "base_repository": self.base_repository,
            "base_changeset": self.base_changeset,
            "head_repository": self.head_repository,
            "head_changeset": self.head_changeset,
            "pull_number": self.pull_number,
        }

    @cached_property
    def pull_request(self):
        from code_review_bot.sources.github import GithubClient

        reporter_conf = next(
            (
                reporter
                for reporter in taskcluster.secrets["REPORTERS"]
                if reporter["reporter"] == "github"
            ),
            None,
        )
        # A github reporter configuration is required to perform a github Pull Request analysis
        assert reporter_conf, "Github reporter secrets must be set to access information about the pull request"
        client = GithubClient(
            client_id=reporter_conf["client_id"],
            private_key=reporter_conf["private_key_pem"],
            installation_id=reporter_conf["installation_id"],
        )
        return client.get_pull_request(self)

    def serialize(self):
        """
        Outputs a tuple of dicts for revision and diff (empty for Github) sent to backend
        """
        revision = {
            "provider": "github",
            "provider_id": self.pull_number,
            "title": self.pull_request.title,
            "bugzilla_id": None,
            "base_repository": self.base_repository,
            "base_changeset": self.base_changeset,
            "head_repository": self.head_repository,
            "head_changeset": self.head_changeset,
        }
        diff = {
            "provider": "github",
            "provider_id": self.head_changeset,
            "mercurial_hash": self.head_changeset,
            "repository": self.base_repository,
        }
        return revision, diff
