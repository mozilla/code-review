# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import hashlib
import random
import uuid

from django.conf import settings
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from code_review_backend.issues.models import Issue, IssueLink, Repository


class StatsAPITestCase(APITestCase):
    def setUp(self):
        # Create a user
        self.user = User.objects.create(username="crash_user")

        # Create a repo & its try
        self.repo = Repository.objects.create(
            id=1, slug="myrepo", url="http://repo.test/myrepo"
        )
        self.repo_try = Repository.objects.create(
            id=2, slug="myrepo-try", url="http://repo.test/myrepo-try"
        )

        # Create a revision
        revision = self.repo_try.head_revisions.create(
            provider="phabricator",
            provider_id=10,
            title="Revision A",
            bugzilla_id=None,
            base_repository=self.repo,
        )

        # Create some diffs
        for i in range(10):
            revision.diffs.create(
                id=i + 1,
                provider_id=f"PHID-DIFF-{i+1}",
                review_task_id=f"task-{i}",
                mercurial_hash=hashlib.sha1(f"hg {i}".encode()).hexdigest(),
                repository=self.repo_try,
            )

        # Create lots of issues randomly affected on diffs
        analyzers = ["analyzer-X", "analyzer-Y", "analyzer-Z"]
        checks = ["check-1", "check-10", "check-42", "check-1000", None]

        issues = Issue.objects.bulk_create(
            [
                Issue(
                    path="path/to/file",
                    level="warning",
                    message=None,
                    analyzer=analyzers[i % len(analyzers)],
                    analyzer_check=checks[i % len(checks)],
                    hash=uuid.uuid4().hex,
                )
                for i in range(500)
            ]
        )
        IssueLink.objects.bulk_create(
            [
                IssueLink(
                    issue=issue,
                    line=random.randint(1, 100),
                    nb_lines=random.randint(1, 100),
                    char=None,
                    revision=revision,
                    diff_id=random.randint(1, 10),
                )
                for issue in issues
            ]
        )

        # Add some issues not attached to a diff
        Issue.objects.bulk_create(
            [
                Issue(
                    path="path/to/file",
                    level="warning",
                    message=None,
                    analyzer=analyzers[i % len(analyzers)],
                    analyzer_check=checks[i % len(checks)],
                    hash=uuid.uuid4().hex,
                )
                for i in range(10)
            ]
        )

        settings.PHABRICATOR_HOST = "http://anotherphab.test/api123/?custom"

    def test_stats(self):
        """
        Check stats generation from the list of random issues
        """
        response = self.client.get("/v1/check/stats/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.maxDiff = None
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
                        "repository": "myrepo-try",
                        "total": 34,
                    },
                    {
                        "analyzer": "analyzer-X",
                        "check": "check-1000",
                        "publishable": 0,
                        "repository": "myrepo-try",
                        "total": 34,
                    },
                    {
                        "analyzer": "analyzer-Y",
                        "check": "check-10",
                        "publishable": 0,
                        "repository": "myrepo-try",
                        "total": 34,
                    },
                    {
                        "analyzer": "analyzer-Y",
                        "check": None,
                        "publishable": 0,
                        "repository": "myrepo-try",
                        "total": 34,
                    },
                    {
                        "analyzer": "analyzer-Z",
                        "check": "check-42",
                        "publishable": 0,
                        "repository": "myrepo-try",
                        "total": 34,
                    },
                    {
                        "analyzer": "analyzer-X",
                        "check": "check-10",
                        "publishable": 0,
                        "repository": "myrepo-try",
                        "total": 33,
                    },
                    {
                        "analyzer": "analyzer-X",
                        "check": "check-42",
                        "publishable": 0,
                        "repository": "myrepo-try",
                        "total": 33,
                    },
                    {
                        "analyzer": "analyzer-X",
                        "check": None,
                        "publishable": 0,
                        "repository": "myrepo-try",
                        "total": 33,
                    },
                    {
                        "analyzer": "analyzer-Y",
                        "check": "check-1",
                        "publishable": 0,
                        "repository": "myrepo-try",
                        "total": 33,
                    },
                    {
                        "analyzer": "analyzer-Y",
                        "check": "check-1000",
                        "publishable": 0,
                        "repository": "myrepo-try",
                        "total": 33,
                    },
                    {
                        "analyzer": "analyzer-Y",
                        "check": "check-42",
                        "publishable": 0,
                        "repository": "myrepo-try",
                        "total": 33,
                    },
                    {
                        "analyzer": "analyzer-Z",
                        "check": "check-1",
                        "publishable": 0,
                        "repository": "myrepo-try",
                        "total": 33,
                    },
                    {
                        "analyzer": "analyzer-Z",
                        "check": "check-10",
                        "publishable": 0,
                        "repository": "myrepo-try",
                        "total": 33,
                    },
                    {
                        "analyzer": "analyzer-Z",
                        "check": "check-1000",
                        "publishable": 0,
                        "repository": "myrepo-try",
                        "total": 33,
                    },
                    {
                        "analyzer": "analyzer-Z",
                        "check": None,
                        "publishable": 0,
                        "repository": "myrepo-try",
                        "total": 33,
                    },
                ],
            },
        )

    def test_details(self):
        """
        Check API endpoint to list issues in a check
        """
        response = self.client.get(
            "/v1/check/myrepo-try/analyzer-X/check-1/?publishable=all"
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
            self.assertEqual(issue["publishable"], 0)
            self.assertEqual(issue["path"], "path/to/file")

            # Diff
            diffs = issue["diffs"]
            self.assertEqual(len(diffs), 1)
            diff = diffs[0]
            self.assertTrue(diff["id"] > 0)
            self.assertEqual(diff["repository"], "http://repo.test/myrepo-try")

            # Revision
            rev = diff["revision"]
            self.assertTrue(rev["id"] > 0)
            self.assertEqual(rev["provider"], "phabricator")
            self.assertTrue(rev["provider_id"] > 0)
            self.assertEqual(rev["base_repository"], "http://repo.test/myrepo")
            self.assertEqual(rev["head_repository"], "http://repo.test/myrepo-try")
            self.assertEqual(
                rev["url"],
                f"http://anotherphab.test/D{rev['provider_id']}",
            )

            return True

        self.assertTrue(all(map(check_issue, data["results"])))
