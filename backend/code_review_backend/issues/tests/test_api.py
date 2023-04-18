# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from code_review_backend.issues.models import Diff, Issue, Repository, Revision


class CreationAPITestCase(APITestCase):
    def setUp(self):
        # Create a user
        self.user = User.objects.create(username="crash_user")

        # Create a repo & its try counterpart
        self.repo = Repository.objects.create(
            id=1, phid="PHID-REPO-xxx", slug="myrepo", url="http://repo.test/myrepo"
        )
        self.repo_try = Repository.objects.create(
            id=2, slug="myrepo-try", url="http://repo.test/try"
        )
        # Create revision and diff
        self.revision = self.repo_try.head_revisions.create(
            numerical_phid=456,
            phid="PHID-REV-XXX",
            title="Bug XXX - Yet Another bug",
            bugzilla_id=78901,
            base_repository=self.repo,
        )
        self.diff = self.revision.diffs.create(
            id=1234,
            phid="PHID-DIFF-xxx",
            review_task_id="deadbeef123",
            mercurial_hash="coffee12345",
            repository=self.repo_try,
        )

    def test_create_revision(self):
        """
        Check we can create a revision through the API
        """
        self.revision.delete()
        data = {
            "numerical_phid": 123,
            "phid": "PHID-REV-xxx",
            "title": "Bug XXX - Some bug",
            "bugzilla_id": 123456,
            "base_repository": "http://repo.test/myrepo",
            "head_repository": "http://repo.test/myrepo",
            "base_changeset": "123456789ABCDEF",
            "head_changeset": "FEDCBA987654321",
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
        revision = Revision.objects.get(numerical_phid=123)
        self.assertEqual(revision.title, "Bug XXX - Some bug")
        self.assertEqual(revision.bugzilla_id, 123456)
        self.assertDictEqual(
            response.json(),
            {
                "id": 2,
                "bugzilla_id": 123456,
                "diffs_url": "http://testserver/v1/revision/2/diffs/",
                "issues_bulk_url": "http://testserver/v1/revision/2/issues/",
                "phabricator_url": "https://phabricator.services.mozilla.com/D123",
                "numerical_phid": 123,
                "phid": "PHID-REV-xxx",
                "base_repository": "http://repo.test/myrepo",
                "head_repository": "http://repo.test/myrepo",
                "base_changeset": "123456789ABCDEF",
                "head_changeset": "FEDCBA987654321",
                "title": "Bug XXX - Some bug",
            },
        )

    def test_create_diff(self):
        """
        Check we can create a diff through the API
        """
        self.diff.delete()
        data = {
            "id": 1234,
            "phid": "PHID-DIFF-xxx",
            "review_task_id": "deadbeef123",
            "mercurial_hash": "coffee12345",
            "repository": "http://repo.test/try",
        }

        # No auth will give a permission denied
        response = self.client.post(
            f"/v1/revision/{self.revision.id}/diffs/", data, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Once authenticated, creation will require the revision to exist
        self.assertEqual(Diff.objects.count(), 0)
        self.client.force_authenticate(user=self.user)
        response = self.client.post("/v1/revision/999999/diffs/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Now creation will work
        self.assertEqual(Diff.objects.count(), 0)
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            f"/v1/revision/{self.revision.id}/diffs/", data, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Response should have url to create issues
        self.assertEqual(
            response.json()["issues_url"], "http://testserver/v1/diff/1234/issues/"
        )

        # Check a diff has been created
        self.assertEqual(Diff.objects.count(), 1)
        diff = Diff.objects.get(pk=1234)
        self.assertEqual(diff.mercurial_hash, "coffee12345")
        self.assertEqual(diff.revision, self.revision)

    def test_create_issue(self):
        """
        Check we can create a issue through the API
        """
        data = {
            "hash": "somemd5hash",
            "line": 1,
            "analyzer": "remote-flake8",
            "level": "error",
            "path": "path/to/file.py",
            "in_patch": True,
        }

        # No auth will give a permission denied
        response = self.client.post("/v1/diff/1234/issues/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Once authenticated, creation will work
        self.assertEqual(Issue.objects.count(), 0)
        self.client.force_authenticate(user=self.user)
        response = self.client.post("/v1/diff/1234/issues/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Do not check the content of issue created as it's a random UUID
        issue_data = response.json()
        self.assertTrue("id" in issue_data)
        del issue_data["id"]
        self.assertDictEqual(
            issue_data,
            {
                "analyzer": "remote-flake8",
                "char": None,
                "check": None,
                "hash": "somemd5hash",
                "level": "error",
                "line": 1,
                "message": None,
                "nb_lines": None,
                "new_for_revision": True,
                "path": "path/to/file.py",
                "in_patch": True,
                "publishable": True,
            },
        )

        # Check a revision has been created
        self.assertEqual(Diff.objects.count(), 1)
        issue = Issue.objects.first()
        self.assertEqual(issue.path, "path/to/file.py")
        self.assertEqual(issue.line, 1)
        self.assertListEqual(
            list(issue.diffs.values_list("id", flat=True)), [self.diff.id]
        )
        self.assertTrue(issue.new_for_revision)

        # The diff now counts an issue
        response = self.client.get("/v1/diff/1234/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["nb_issues"], 1)

    def test_create_issue_bulk_methods(self):
        self.client.force_authenticate(user=self.user)
        for method in ("get", "put", "patch"):
            response = getattr(self.client, method)("/v1/revision/456/issues/")
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_create_issue_wrong_revision(self):
        self.client.force_authenticate(user=self.user)
        with self.assertNumQueries(1):
            response = self.client.post(
                "/v1/revision/0011101000101001/issues/", {}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_issue_bulk(self):
        """
        Check we can create multiple issues through the API without no Diff
        """
        data = {
            "issues": [
                {
                    "hash": "somemd5hash",
                    "line": 1,
                    "analyzer": "remote-flake8",
                    "level": "error",
                    "path": "path/to/file.py",
                    "in_patch": True,
                    "new_for_revision": False,
                },
                {
                    "hash": "anothermd5hash",
                    "line": 2,
                    "analyzer": "test",
                    "level": "warning",
                    "path": "path/to/file.py",
                    "in_patch": False,
                },
            ]
        }

        # No auth will give a permission denied
        response = self.client.post(
            f"/v1/revision/{self.revision.id}/issues/", data, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Once authenticated, creation will work
        self.assertEqual(Issue.objects.count(), 0)
        self.client.force_authenticate(user=self.user)
        with self.assertNumQueries(5):
            response = self.client.post(
                f"/v1/revision/{self.revision.id}/issues/", data, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        issues = list(Issue.objects.order_by("created"))
        self.assertEqual(len(issues), 2)

        # Do not check the content of issue created as it's a random UUID
        issue_data = response.json()
        self.assertDictEqual(
            issue_data,
            {
                "diff_id": None,
                "issues": [
                    {
                        "analyzer": "remote-flake8",
                        "char": None,
                        "check": None,
                        "hash": "somemd5hash",
                        "id": str(issues[0].id),
                        "in_patch": True,
                        "level": "error",
                        "line": 1,
                        "message": None,
                        "nb_lines": None,
                        "new_for_revision": None,
                        "path": "path/to/file.py",
                        "publishable": True,
                    },
                    {
                        "analyzer": "test",
                        "char": None,
                        "check": None,
                        "hash": "anothermd5hash",
                        "id": str(issues[1].id),
                        "in_patch": False,
                        "level": "warning",
                        "line": 2,
                        "message": None,
                        "nb_lines": None,
                        "new_for_revision": None,
                        "path": "path/to/file.py",
                        "publishable": False,
                    },
                ],
            },
        )

        self.assertEqual(issues[0].path, "path/to/file.py")
        self.assertEqual(issues[0].line, 1)
        self.assertFalse(issues[0].diffs.exists())
        self.assertFalse(issues[0].new_for_revision)

        self.assertEqual(issues[1].path, "path/to/file.py")
        self.assertEqual(issues[1].line, 2)
        self.assertFalse(issues[1].diffs.exists())
        self.assertEqual(issues[1].new_for_revision, None)

    def test_create_issue_bulk_with_diff(self):
        """
        Check we can create issues on a revision with a reference to a diff
        """
        data = {
            "diff_id": 1234,
            "issues": [
                {
                    "hash": "somemd5hash",
                    "line": 1,
                    "analyzer": "remote-flake8",
                    "level": "error",
                    "path": "path/to/file.py",
                    "in_patch": True,
                    "new_for_revision": False,
                }
            ],
        }
        self.client.force_authenticate(user=self.user)
        with self.assertNumQueries(6):
            response = self.client.post(
                f"/v1/revision/{self.revision.id}/issues/", data, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(Issue.objects.filter(revisions__numerical_phid=456).count(), 1)

        issue = Issue.objects.filter(revisions__numerical_phid=456).get()
        self.assertDictEqual(
            response.json(),
            {
                "diff_id": 1234,
                "issues": [
                    {
                        "analyzer": "remote-flake8",
                        "char": None,
                        "check": None,
                        "hash": "somemd5hash",
                        "id": str(issue.id),
                        "in_patch": True,
                        "level": "error",
                        "line": 1,
                        "message": None,
                        "nb_lines": None,
                        "new_for_revision": None,
                        "path": "path/to/file.py",
                        "publishable": True,
                    },
                ],
            },
        )

        self.assertEqual(issue.path, "path/to/file.py")
        self.assertEqual(issue.line, 1)
        self.assertListEqual(
            list(issue.diffs.values_list("id", flat=True)), [self.diff.id]
        )
        self.assertFalse(issue.new_for_revision)
