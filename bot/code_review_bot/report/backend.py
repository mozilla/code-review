# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import urllib.parse

import requests
import structlog

from code_review_bot.config import settings
from code_review_bot.report.base import Reporter

logger = structlog.get_logger(__name__)


class BackendReporter(Reporter):
    """
    Publish the issues on our backend for further analysis
    """

    def __init__(self, configuration):
        assert "url" in configuration, "Missing backend url"
        assert "username" in configuration, "Missing backend username"
        assert "password" in configuration, "Missing backend password"
        self.url = configuration["url"]
        self.username = configuration["username"]
        self.password = configuration["password"]
        logger.info("Will publish issues on backend", url=self.url, user=self.username)

    def publish(self, issues, revision):
        """
        Display issues choices
        """

        # Create revision on backend if it does not exists
        data = {
            "id": revision.id,
            "phid": revision.phid,
            "title": revision.title,
            "bugzilla_id": revision.bugzilla_id,
            "repository": revision.target_repository,
        }
        backend_revision = self.create("/v1/revision/", data)

        # Create diff on backend
        data = {
            "id": revision.diff_id,
            "phid": revision.diff_phid,
            "revision": backend_revision["id"],
            "review_task_id": settings.taskcluster.task_id,
            "mercurial_hash": revision.mercurial_revision,
        }
        backend_diff = self.create("/v1/diff/", data)

        # Publish each issue on the backend
        for issue in issues:
            self.create(backend_diff["issues_url"], issue.as_dict())

        logger.info("Published all issues on backend")

    def create(self, url_path, data):
        """
        Make an authenticated POST request on the backend
        Check that the requested item does not already exists on the backend
        """
        assert url_path.endswith("/")
        auth = (self.username, self.password)

        if "id" in data:
            # Check that the item does not already exists
            url_get = urllib.parse.urljoin(self.url, f"{url_path}{data['id']}/")
            response = requests.get(url_get, auth=auth)
            if response.ok:
                logger.info("Found existing item on backend", url=url_get)
                return response.json()

        # Create the requested item
        url_post = urllib.parse.urljoin(self.url, url_path)
        response = requests.post(
            url_post, json=data, auth=(self.username, self.password)
        )
        if not response.ok:
            logger.warn("Backend rejected the payload: {}".format(response.content))
        response.raise_for_status()
        out = response.json()
        logger.info("Created item on backend", url=url_post, id=out["id"])
        return out
