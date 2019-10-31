# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from code_review_backend.issues.models import Diff
from code_review_backend.issues.models import Issue
from code_review_backend.issues.models import Repository
from code_review_backend.issues.models import Revision


class CreationAPITestCase(APITestCase):
    def setUp(self):
        # Create a user
        self.user = User.objects.create(username="crash_user")

        # Create a repo
        self.repo = Repository.objects.create(
            id=1, phid="PHID-REPO-xxx", slug="myrepo", url="http://repo.test/myrepo"
        )

    def test_create_revision(self):
        """
        Check we can create a revision through the API
        """
        data = {
            "id": 123,
            "phid": "PHID-REV-xxx",
            "title": "Bug XXX - Some bug",
            "bugzilla_id": 123456,
            "repository": "myrepo",
        }

        # No auth will give a permission denied
        response = self.client.post("/v1/revision/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Once authenticated, creation will work
        self.assertEqual(Revision.objects.count(), 0)
        self.client.force_authenticate(user=self.user)
        response = self.client.post("/v1/revision/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Check a revision has been created
        self.assertEqual(Revision.objects.count(), 1)
        revision = Revision.objects.get(pk=123)
        self.assertEqual(revision.title, "Bug XXX - Some bug")
        self.assertEqual(revision.bugzilla_id, 123456)

    def test_create_diff(self):
        """
        Check we can create a diff through the API
        """
        data = {
            "id": 1234,
            "phid": "PHID-DIFF-xxx",
            "review_task_id": "deadbeef123",
            "analyzers_group_id": "bigGroupId",
            "mercurial_hash": "coffee12345",
        }

        # No auth will give a permission denied
        response = self.client.post("/v1/revision/123/diffs/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Once authenticated, creation will require the revision to exist
        self.assertEqual(Diff.objects.count(), 0)
        self.client.force_authenticate(user=self.user)
        response = self.client.post("/v1/revision/123/diffs/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Create the requested revision
        revision = Revision.objects.create(
            id=123,
            phid="PHID-REV-XXX",
            repository=self.repo,
            title="Bug XXX - Another bug",
            bugzilla_id=123456,
        )

        # Now creation will work
        self.assertEqual(Diff.objects.count(), 0)
        self.client.force_authenticate(user=self.user)
        response = self.client.post("/v1/revision/123/diffs/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Response should have url to create issues
        self.assertEqual(
            response.json()["issues_url"], "http://testserver/v1/diff/1234/issues/"
        )

        # Check a diff has been created
        self.assertEqual(Diff.objects.count(), 1)
        diff = Diff.objects.get(pk=1234)
        self.assertEqual(diff.mercurial_hash, "coffee12345")
        self.assertEqual(diff.revision, revision)
        self.assertEqual(diff.analyzers_group_id, "bigGroupId")
        self.assertEqual(diff.review_task_id, "deadbeef123")

    def test_create_issue(self):
        """
        Check we can create a issue through the API
        """
        # Create revision and diff
        revision = self.repo.revisions.create(
            id=456,
            phid="PHID-REV-XXX",
            title="Bug XXX - Yet Another bug",
            bugzilla_id=78901,
        )
        diff = revision.diffs.create(
            id=1234,
            phid="PHID-DIFF-xxx",
            review_task_id="deadbeef123",
            mercurial_hash="coffee12345",
        )

        data = {
            "hash": "somemd5hash",
            "line": 1,
            "analyzer": "remote-flake8",
            "level": "error",
            "path": "path/to/file.py",
        }

        # No auth will give a permission denied
        response = self.client.post("/v1/diff/1234/issues/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Once authenticated, creation will work
        self.assertEqual(Issue.objects.count(), 0)
        self.client.force_authenticate(user=self.user)
        response = self.client.post("/v1/diff/1234/issues/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Check a revision has been created
        self.assertEqual(Diff.objects.count(), 1)
        issue = Issue.objects.first()
        self.assertEqual(issue.path, "path/to/file.py")
        self.assertEqual(issue.line, 1)
        self.assertEqual(issue.diff, diff)
        self.assertEqual(issue.diff.revision, revision)

        # The diff now counts an issue
        response = self.client.get("/v1/diff/1234/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["nb_issues"], 1)
