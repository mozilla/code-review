# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import hashlib
import random
import uuid

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from code_review_backend.issues.models import Issue
from code_review_backend.issues.models import Repository


class StatsAPITestCase(APITestCase):
    def setUp(self):
        # Create a user
        self.user = User.objects.create(username="crash_user")

        # Create a repo & its try
        self.repo = Repository.objects.create(
            id=1, phid="PHID-REPO-xxx", slug="myrepo", url="http://repo.test/myrepo"
        )
        self.repo_try = Repository.objects.create(
            id=2, slug="myrepo-try", url="http://repo.test/myrepo-try"
        )

        # Create a revision
        revision = self.repo.revisions.create(
            id=10, phid=f"PHID-DREV-arev", title=f"Revision A", bugzilla_id=None
        )

        # Create some diffs
        for i in range(10):
            revision.diffs.create(
                id=i + 1,
                phid=f"PHID-DIFF-{i+1}",
                review_task_id=f"task-{i}",
                mercurial_hash=hashlib.sha1(f"hg {i}".encode("utf-8")).hexdigest(),
                repository=self.repo_try,
            )

        # Create lots of issues randomly affected on diffs
        analyzers = ["analyzer-X", "analyzer-Y", "analyzer-Z"]
        checks = ["check-1", "check-10", "check-42", "check-1000", None]

        for i in range(500):
            Issue.objects.create(
                diff_id=random.randint(1, 10),
                path="path/to/file",
                line=random.randint(1, 100),
                nb_lines=random.randint(1, 100),
                char=None,
                level="warning",
                message=None,
                analyzer=analyzers[i % len(analyzers)],
                check=checks[i % len(checks)],
                hash=uuid.uuid4().hex,
            )

        # Add some issues not attached to a diff
        for i in range(10):
            Issue.objects.create(
                diff_id=None,
                path="path/to/file",
                line=random.randint(1, 100),
                nb_lines=random.randint(1, 100),
                char=None,
                level="warning",
                message=None,
                analyzer=analyzers[i % len(analyzers)],
                check=checks[i % len(checks)],
                hash=uuid.uuid4().hex,
            )

    def test_stats(self):
        """
        Check stats generation from the list of random issues
        """
        self.maxDiff = None
        response = self.client.get("/v1/check/stats/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictEqual(
            response.json(),
            {
                "count": 25,
                "next": None,
                "previous": None,
                "results": [
                    {
                        "analyzer": "analyzer-X",
                        "check": "check-1",
                        "publishable": 0,
                        "repository": "myrepo",
                        "total": 34,
                    },
                    {
                        "analyzer": "analyzer-X",
                        "check": "check-1000",
                        "publishable": 0,
                        "repository": "myrepo",
                        "total": 34,
                    },
                    {
                        "analyzer": "analyzer-Y",
                        "check": None,
                        "publishable": 0,
                        "repository": "myrepo",
                        "total": 34,
                    },
                    {
                        "analyzer": "analyzer-Y",
                        "check": "check-10",
                        "publishable": 0,
                        "repository": "myrepo",
                        "total": 34,
                    },
                    {
                        "analyzer": "analyzer-Z",
                        "check": "check-42",
                        "publishable": 0,
                        "repository": "myrepo",
                        "total": 34,
                    },
                    {
                        "analyzer": "analyzer-X",
                        "check": None,
                        "publishable": 0,
                        "repository": "myrepo",
                        "total": 33,
                    },
                    {
                        "analyzer": "analyzer-X",
                        "check": "check-10",
                        "publishable": 0,
                        "repository": "myrepo",
                        "total": 33,
                    },
                    {
                        "analyzer": "analyzer-X",
                        "check": "check-42",
                        "publishable": 0,
                        "repository": "myrepo",
                        "total": 33,
                    },
                    {
                        "analyzer": "analyzer-Y",
                        "check": "check-1",
                        "publishable": 0,
                        "repository": "myrepo",
                        "total": 33,
                    },
                    {
                        "analyzer": "analyzer-Y",
                        "check": "check-1000",
                        "publishable": 0,
                        "repository": "myrepo",
                        "total": 33,
                    },
                    {
                        "analyzer": "analyzer-Y",
                        "check": "check-42",
                        "publishable": 0,
                        "repository": "myrepo",
                        "total": 33,
                    },
                    {
                        "analyzer": "analyzer-Z",
                        "check": None,
                        "publishable": 0,
                        "repository": "myrepo",
                        "total": 33,
                    },
                    {
                        "analyzer": "analyzer-Z",
                        "check": "check-1",
                        "publishable": 0,
                        "repository": "myrepo",
                        "total": 33,
                    },
                    {
                        "analyzer": "analyzer-Z",
                        "check": "check-10",
                        "publishable": 0,
                        "repository": "myrepo",
                        "total": 33,
                    },
                    {
                        "analyzer": "analyzer-Z",
                        "check": "check-1000",
                        "publishable": 0,
                        "repository": "myrepo",
                        "total": 33,
                    },
                    {
                        "analyzer": "analyzer-X",
                        "check": None,
                        "publishable": 0,
                        "repository": None,
                        "total": 1,
                    },
                    {
                        "analyzer": "analyzer-X",
                        "check": "check-1",
                        "publishable": 0,
                        "repository": None,
                        "total": 1,
                    },
                    {
                        "analyzer": "analyzer-X",
                        "check": "check-10",
                        "publishable": 0,
                        "repository": None,
                        "total": 1,
                    },
                    {
                        "analyzer": "analyzer-X",
                        "check": "check-1000",
                        "publishable": 0,
                        "repository": None,
                        "total": 1,
                    },
                    {
                        "analyzer": "analyzer-Y",
                        "check": None,
                        "publishable": 0,
                        "repository": None,
                        "total": 1,
                    },
                    {
                        "analyzer": "analyzer-Y",
                        "check": "check-10",
                        "publishable": 0,
                        "repository": None,
                        "total": 1,
                    },
                    {
                        "analyzer": "analyzer-Y",
                        "check": "check-42",
                        "publishable": 0,
                        "repository": None,
                        "total": 1,
                    },
                    {
                        "analyzer": "analyzer-Z",
                        "check": "check-1",
                        "publishable": 0,
                        "repository": None,
                        "total": 1,
                    },
                    {
                        "analyzer": "analyzer-Z",
                        "check": "check-1000",
                        "publishable": 0,
                        "repository": None,
                        "total": 1,
                    },
                    {
                        "analyzer": "analyzer-Z",
                        "check": "check-42",
                        "publishable": 0,
                        "repository": None,
                        "total": 1,
                    },
                ],
            },
        )

    def test_details(self):
        """
        Check API endpoint to list issues in a check
        """
        self.maxDiff = None
        response = self.client.get(
            "/v1/check/myrepo/analyzer-X/check-1/?publishable=all"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["count"], 34)
        self.assertEqual(len(data["results"]), 34)

        def check_issue(issue):
            """Check issue without straight comparison as several fields are random"""

            # Base fields
            self.assertEqual(issue["analyzer"], "analyzer-X")
            self.assertEqual(issue["check"], "check-1")
            self.assertEqual(issue["level"], "warning")
            self.assertIsNone(issue["message"])
            self.assertIsNone(issue["in_patch"])
            self.assertFalse(issue["publishable"])
            self.assertEqual(issue["path"], "path/to/file")

            # Diff
            diff = issue["diff"]
            self.assertTrue(diff["id"] > 0)
            self.assertEqual(diff["repository"], "http://repo.test/myrepo-try")

            # Revision
            rev = diff["revision"]
            self.assertTrue(rev["id"] > 0)
            self.assertEqual(rev["repository"], "http://repo.test/myrepo")
            self.assertEqual(
                rev["phabricator_url"], f"http://anotherphab.test/D{rev['id']}"
            )

            return True

        self.assertTrue(all(map(check_issue, data["results"])))
