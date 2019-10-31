# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import urllib.parse

import requests
import structlog

from code_review_bot import taskcluster
from code_review_bot.config import settings

logger = structlog.get_logger(__name__)


class BackendAPI(object):
    """
    API client for our own code-review backend
    """

    def __init__(self):
        configuration = taskcluster.secrets.get("backend", {})
        self.url = configuration.get("url")
        self.username = configuration.get("username")
        self.password = configuration.get("password")
        if self.enabled:
            logger.info("Will use backend", url=self.url, user=self.username)
        else:
            logger.info("Skipping backend storage")

    @property
    def enabled(self):
        return (
            self.url is not None
            and self.username is not None
            and self.password is not None
        )

    def publish_revision(self, revision):
        """
        Create Revision and Diff instances in backend
        """
        if not self.enabled:
            logger.warn("Skipping revision publication on backend")
            return

        # Create revision on backend if it does not exists
        data = {
            "id": revision.id,
            "phid": revision.phid,
            "title": revision.title,
            "bugzilla_id": revision.bugzilla_id,
            "repository": revision.target_repository,
        }
        backend_revision = self.create("/v1/revision/", data)

        # Create diff attached to revision on backend
        data = {
            "id": revision.diff_id,
            "phid": revision.diff_phid,
            "review_task_id": settings.taskcluster.task_id,
            "analyzers_group_id": settings.try_group_id,
            "mercurial_hash": revision.mercurial_revision,
        }
        backend_diff = self.create(backend_revision["diffs_url"], data)

        # Store the issues url on the revision
        revision.issues_url = backend_diff["issues_url"]

    def publish_issues(self, issues, revision):
        """
        Publish all issues on the backend
        """
        if not self.enabled:
            logger.warn("Skipping issues publication on backend")
            return

        assert revision.issues_url is not None, "Missing issues_url on revision"
        for issue in issues:
            self.create(revision.issues_url, issue.as_dict())

        logger.info("Published all issues on backend")

    def create(self, url_path, data):
        """
        Make an authenticated POST request on the backend
        Check that the requested item does not already exists on the backend
        """
        assert self.enabled is True, "Backend API is not enabled"
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
        response = requests.post(url_post, json=data, auth=auth)
        if not response.ok:
            logger.warn("Backend rejected the payload: {}".format(response.content))
        response.raise_for_status()
        out = response.json()
        logger.info("Created item on backend", url=url_post, id=out["id"])
        return out
