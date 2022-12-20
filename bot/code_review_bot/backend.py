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

        # Check the repositories are urls
        for url in (revision.target_repository, revision.repository):
            assert isinstance(url, str), "Repository must be a string"
            res = urllib.parse.urlparse(url)
            assert res.scheme and res.netloc, f"Repository {url} is not an url"

        # Create revision on backend if it does not exists
        data = {
            "id": revision.id,
            "phid": revision.phid,
            "title": revision.title,
            "bugzilla_id": revision.bugzilla_id,
            "repository": revision.target_repository,
        }
        backend_revision = self.create("/v1/revision/", data)

        # If we are dealing with None `backend_revision` bail out
        if backend_revision is None:
            return

        # Create diff attached to revision on backend
        data = {
            "id": revision.diff_id,
            "phid": revision.diff_phid,
            "review_task_id": settings.taskcluster.task_id,
            "mercurial_hash": revision.mercurial_revision,
            "repository": revision.repository,
        }
        backend_diff = self.create(backend_revision["diffs_url"], data)

        # If we are dealing with a None `backend_revision` bail out
        if backend_diff is None:
            revision.issues_url = None
            return

        # Store the issues url on the revision
        revision.issues_url = backend_diff["issues_url"]

    def publish_issues(self, issues, revision, mercurial_repository=None, bulk=0):
        """
        Publish all issues on the backend.
        `mercurial_repository` parameter should be path to the local repository at the given revision.
        If set to an integer, `bulk` parameter allow to use the bulk creation endpoint of the backend.
        """
        if not self.enabled:
            logger.warn("Skipping issues publication on backend")
            return

        if revision.issues_url is None:
            logger.warn(
                "Missing issues_url on revision",
            )
            return

        published = 0
        if bulk > 0:
            url = revision.issues_url.rstrip("/") + "-bulk/"
            chunks = (issues[i : i + bulk] for i in range(0, len(issues), bulk))
            for issues_chunk in chunks:
                data = []
                # Build issues' payload for that given chunk
                for issue in issues_chunk:
                    issue_hash = issue.build_hash(local_repository=mercurial_repository)
                    if issue_hash is None:
                        logger.warning(
                            "Missing issue hash, cannot publish on backend",
                            issue=str(issue),
                        )
                        continue
                    data.append(issue.as_dict(issue_hash=issue_hash))
                response = self.create(url, {"issues": data})
                created = response.get("issues")
                assert created and len(created) == len(issues_chunk)
                for issue, value in zip(issues_chunk, created):
                    # Set the returned value on each issue
                    issue.on_backend = value
                published += len(data)
        else:
            for issue in issues:
                issue_hash = issue.build_hash(local_repository=mercurial_repository)
                if issue_hash is None:
                    logger.warning(
                        "Missing issue hash, cannot publish on backend",
                        issue=str(issue),
                    )
                    continue
                payload = issue.as_dict(issue_hash=issue_hash)
                issue.on_backend = self.create(revision.issues_url, payload)
                if issue.on_backend is not None:
                    published += 1
                else:
                    logger.warn("Failed backend publication", issue=str(issue))

        total = len(issues)
        if published < total:
            logger.warn(
                "Published a subset of issues", total=total, published=published
            )
        else:
            logger.info("Published all issues on backend", nb=published)

        return published

    def list_diff_issues(self, diff_id):
        """
        List issues for a given diff
        """
        return list(self.paginate(f"/v1/diff/{diff_id}/issues/"))

    def paginate(self, url_path):
        """
        Yield results from a paginated API one by one
        """
        auth = (self.username, self.password)
        next_url = urllib.parse.urljoin(self.url, url_path)

        # Iterate until there is no page left or a status error happen
        while next_url:
            resp = requests.get(next_url, auth=auth)
            resp.raise_for_status()
            data = resp.json()
            for result in data.get("results", []):
                yield result
            next_url = data.get("next")

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
            return None
        out = response.json()
        logger.info("Created item on backend", url=url_post, id=out.get("id"))
        return out
