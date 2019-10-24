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

        # Create a repo
        self.repo = Repository.objects.create(
            id=1, phid="PHID-REPO-xxx", slug="myrepo", url="http://repo.test/myrepo"
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
                "count": 15,
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
                ],
            },
        )
