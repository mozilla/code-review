# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import urllib.parse

import requests
import structlog

from code_review_bot import taskcluster
from code_review_bot.config import GetAppUserAgent, settings
from code_review_bot.tasks.lint import MozLintIssue

logger = structlog.get_logger(__name__)


class BackendAPI:
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
        Create a Revision on the backend.
        In case revision.diff_id exists, also create revision's diff.
        """
        if not self.enabled:
            logger.warn("Skipping revision publication on backend")
            return

        # Check the repositories are urls
        for url in (revision.base_repository, revision.head_repository):
            assert isinstance(url, str), "Repository must be a string"
            res = urllib.parse.urlparse(url)
            assert res.scheme and res.netloc, f"Repository {url} is not an url"

        # Check the Mercurial changesets are strings
        for changeset in (
            revision.base_changeset,
            revision.head_changeset,
        ):
            assert isinstance(changeset, str), "Mercurial changeset must be a string"

        # Create revision on backend if it does not exists
        data = {
            "phabricator_id": revision.phabricator_id,
            "phabricator_phid": revision.phabricator_phid,
            "title": revision.title,
            "bugzilla_id": revision.bugzilla_id,
            "base_repository": revision.base_repository,
            "head_repository": revision.head_repository,
            "base_changeset": revision.base_changeset,
            "head_changeset": revision.head_changeset,
        }

        # Try to create the revision, or retrieve it in case it exists with that Phabricator ID.
        # The backend always returns a revisions, either a new one, or a pre-existing one
        revision_url = "/v1/revision/"
        auth = (self.username, self.password)
        url_post = urllib.parse.urljoin(self.url, revision_url)
        response = requests.post(
            url_post, headers=GetAppUserAgent(), json=data, auth=auth
        )
        if not response.ok:
            logger.warn(f"Backend rejected the payload: {response.content}")
            return

        backend_revision = response.json()
        revision.issues_url = backend_revision["issues_bulk_url"]
        revision.id = backend_revision["id"]

        # A revision may have no diff (e.g. Mozilla-central group tasks)
        if not revision.diff_id:
            return backend_revision

        # Create diff attached to revision on backend
        data = {
            "id": revision.diff_id,
            "phid": revision.diff_phid,
            "review_task_id": settings.taskcluster.task_id,
            "mercurial_hash": revision.head_changeset,
            "repository": revision.head_repository,
        }
        backend_diff = self.create(backend_revision["diffs_url"], data)

        # If we are dealing with a None `backend_revision` bail out
        if backend_diff is None:
            return backend_revision

        return backend_revision

    def publish_issues(self, issues, revision):
        """
        Publish all issues on the backend in bulk.
        """
        if not self.enabled:
            logger.warn("Skipping issues publication on backend")
            return

        published = 0
        assert (
            revision.issues_url is not None
        ), "Missing issues_url on the revision to publish issues in bulk."

        logger.info(f"Publishing issues in bulk of {settings.bulk_issue_chunks} items.")
        chunks = (
            issues[i : i + settings.bulk_issue_chunks]
            for i in range(0, len(issues), settings.bulk_issue_chunks)
        )
        for issues_chunk in chunks:
            # Store valid data as couples of (<issue>, <json_data>)
            valid_data = []
            # Build issues' payload for that given chunk
            for issue in issues_chunk:
                if (
                    isinstance(issue, MozLintIssue)
                    and issue.linter == "rust"
                    and issue.path == "."
                ):
                    # Silently ignore issues with path "." from rustfmt, as they cannot be published
                    # https://github.com/mozilla/code-review/issues/1577
                    continue
                if issue.hash is None:
                    logger.warning(
                        "Missing issue hash, cannot publish on backend",
                        issue=str(issue),
                    )
                    continue
                valid_data.append((issue, issue.as_dict()))

            if not valid_data:
                # May happen when a series of issues are missing a hash
                logger.warning(
                    "No issue is valid over an entire chunk",
                    head_repository=revision.head_repository,
                    head_changeset=revision.head_changeset,
                )
                continue

            response = self.create(
                revision.issues_url,
                {"issues": [json_data for _, json_data in valid_data]},
            )
            if response is None:
                # Backend rejected the payload, nothing more to do.
                continue
            created = response.get("issues")

            assert created and len(created) == len(valid_data)
            for (issue, _), return_value in zip(valid_data, created):
                # Set the returned value on each issue
                issue.on_backend = return_value

            published += len(valid_data)

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

    def list_diff_issues_v2(self, diff_id, mode):
        """
        List issues for a given dif
        """
        assert mode in ("known", "unresolved", "closed")
        return list(self.paginate(f"/v2/diff/{diff_id}/issues/{mode}"))

    def paginate(self, url_path):
        """
        Yield results from a paginated API one by one
        """
        auth = (self.username, self.password)
        next_url = urllib.parse.urljoin(self.url, url_path)

        # Iterate until there is no page left or a status error happen
        while next_url:
            resp = requests.get(next_url, auth=auth, headers=GetAppUserAgent())
            resp.raise_for_status()
            data = resp.json()
            yield from data.get("results", [])
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
            response = requests.get(url_get, auth=auth, headers=GetAppUserAgent())
            if response.ok:
                logger.info("Found existing item on backend", url=url_get)
                return response.json()

        # Create the requested item
        url_post = urllib.parse.urljoin(self.url, url_path)
        response = requests.post(
            url_post, headers=GetAppUserAgent(), json=data, auth=auth
        )
        if not response.ok:
            logger.warn(f"Backend rejected the payload: {response.content}")
            return None
        out = response.json()
        logger.info("Created item on backend", url=url_post, id=out.get("id"))
        return out

    def list_repo_issues(
        self, repo_slug, date=None, revision_changeset=None, path=None
    ):
        """
        List issues detected from a specific repository.
        Optional `date` and `revision_id` parameters can be used to look for a
        specific revision (defaults to the revision closest to the given date).
        """
        params = {
            key: value
            for key, value in (
                ("path", path),
                ("date", date),
                ("revision_changeset", revision_changeset),
            )
            if value is not None
        }
        return list(
            self.paginate(f"/v1/issues/{repo_slug}/?{urllib.parse.urlencode(params)}")
        )
