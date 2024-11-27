# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import hashlib
from datetime import datetime

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from code_review_backend.issues.models import Diff, Repository


class DiffAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        # Create a user
        cls.user = User.objects.create(username="crash_user")

        # Create a repo & its try counterpart
        cls.repo = Repository.objects.create(
            id=1, slug="myrepo", url="http://repo.test/myrepo"
        )
        cls.repo_try = Repository.objects.create(
            id=2, slug="myrepo-try", url="http://repo.test/try"
        )

        # Create a stack with 2 revisions & 3 diffs
        for i in range(2):
            cls.repo_try.head_revisions.create(
                id=i + 1,
                phabricator_id=i + 1,
                phabricator_phid=f"PHID-DREV-{i+1}",
                title=f"Revision {i+1}",
                bugzilla_id=10000 + i,
                base_repository=cls.repo,
            )
        for i in range(3):
            Diff.objects.create(
                id=i + 1,
                phid=f"PHID-DIFF-{i+1}",
                revision_id=(i % 2) + 1,
                review_task_id=f"task-{i}",
                mercurial_hash=hashlib.sha1(f"hg {i}".encode()).hexdigest(),
                repository=cls.repo_try,
            )

        # Force created date update without using inner django trigger
        # so that all diffs in the test have the same date to be able
        # to compare the payload easily
        cls.now = datetime.utcnow().isoformat() + "Z"
        Diff.objects.update(created=cls.now)

    def test_list_diffs(self):
        """
        Check we can list all diffs with their revision
        """
        response = self.client.get("/v1/diff/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictEqual(
            response.json(),
            {
                "count": 3,
                "next": None,
                "previous": None,
                "results": [
                    {
                        "id": 3,
                        "revision": {
                            "id": 1,
                            "base_repository": "http://repo.test/myrepo",
                            "head_repository": "http://repo.test/try",
                            "base_changeset": None,
                            "head_changeset": None,
                            "phabricator_id": 1,
                            "phabricator_phid": "PHID-DREV-1",
                            "title": "Revision 1",
                            "bugzilla_id": 10000,
                            "diffs_url": "http://testserver/v1/revision/1/diffs/",
                            "issues_bulk_url": "http://testserver/v1/revision/1/issues/",
                            "phabricator_url": "https://phabricator.services.mozilla.com/D1",
                        },
                        "repository": {
                            "id": 2,
                            "slug": "myrepo-try",
                            "url": "http://repo.test/try",
                        },
                        "phid": "PHID-DIFF-3",
                        "review_task_id": "task-2",
                        "mercurial_hash": "30b501affc4d3b9c670fc297ab903b406afd5f04",
                        "issues_url": "http://testserver/v1/diff/3/issues/",
                        "nb_issues": 0,
                        "nb_issues_publishable": 0,
                        "nb_warnings": 0,
                        "nb_errors": 0,
                        "created": self.now,
                    },
                    {
                        "id": 2,
                        "revision": {
                            "id": 2,
                            "base_repository": "http://repo.test/myrepo",
                            "head_repository": "http://repo.test/try",
                            "base_changeset": None,
                            "head_changeset": None,
                            "phabricator_id": 2,
                            "phabricator_phid": "PHID-DREV-2",
                            "title": "Revision 2",
                            "bugzilla_id": 10001,
                            "diffs_url": "http://testserver/v1/revision/2/diffs/",
                            "issues_bulk_url": "http://testserver/v1/revision/2/issues/",
                            "phabricator_url": "https://phabricator.services.mozilla.com/D2",
                        },
                        "repository": {
                            "id": 2,
                            "slug": "myrepo-try",
                            "url": "http://repo.test/try",
                        },
                        "phid": "PHID-DIFF-2",
                        "review_task_id": "task-1",
                        "mercurial_hash": "32d2a594cfef74fcb524028d1521d0d4bd98bd35",
                        "issues_url": "http://testserver/v1/diff/2/issues/",
                        "nb_issues": 0,
                        "nb_issues_publishable": 0,
                        "nb_warnings": 0,
                        "nb_errors": 0,
                        "created": self.now,
                    },
                    {
                        "id": 1,
                        "revision": {
                            "id": 1,
                            "base_repository": "http://repo.test/myrepo",
                            "head_repository": "http://repo.test/try",
                            "base_changeset": None,
                            "head_changeset": None,
                            "phabricator_id": 1,
                            "phabricator_phid": "PHID-DREV-1",
                            "title": "Revision 1",
                            "bugzilla_id": 10000,
                            "diffs_url": "http://testserver/v1/revision/1/diffs/",
                            "issues_bulk_url": "http://testserver/v1/revision/1/issues/",
                            "phabricator_url": "https://phabricator.services.mozilla.com/D1",
                        },
                        "repository": {
                            "id": 2,
                            "slug": "myrepo-try",
                            "url": "http://repo.test/try",
                        },
                        "phid": "PHID-DIFF-1",
                        "review_task_id": "task-0",
                        "mercurial_hash": "a2ac78b7d12d6e55b9b15c1c2048a16c58c6c803",
                        "issues_url": "http://testserver/v1/diff/1/issues/",
                        "nb_issues": 0,
                        "nb_issues_publishable": 0,
                        "nb_warnings": 0,
                        "nb_errors": 0,
                        "created": self.now,
                    },
                ],
            },
        )

    def test_filter_repo(self):
        """
        Check we can filter diffs by repo
        """

        # Exact repo
        response = self.client.get("/v1/diff/?repository=myrepo")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["count"], 3)
        self.assertEqual([d["id"] for d in response.json()["results"]], [3, 2, 1])

        # Missing repo
        response = self.client.get("/v1/diff/?repository=missing")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["count"], 0)

    def test_search(self):
        """
        Check we can search across diffs
        """

        # In bugzilla id
        response = self.client.get("/v1/diff/?search=10001")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual([d["id"] for d in response.json()["results"]], [2])

        # In title
        response = self.client.get("/v1/diff/?search=revision 1")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["count"], 2)
        self.assertEqual([d["id"] for d in response.json()["results"]], [3, 1])

    def test_filter_issues(self):
        """
        Check we can filter by issues present or not
        """

        # No issues at all
        response = self.client.get("/v1/diff/?issues=no")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["count"], 3)
        self.assertEqual([d["id"] for d in response.json()["results"]], [3, 2, 1])

        # Any issues
        response = self.client.get("/v1/diff/?issues=any")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["count"], 0)
