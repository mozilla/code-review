# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import datetime
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status

from code_review_backend.issues.models import (
    LEVEL_ERROR,
    LEVEL_WARNING,
    Issue,
    Repository,
)


class IssueTestCase(TestCase):
    def setUp(self):
        self.repo = Repository.objects.create(id=42, slug="repo_slug")
        with patch("django.utils.timezone.now") as mock_now:
            mock_now.return_value = datetime.fromisoformat("2010-01-01:10")
            self.revision = self.repo.base_revisions.create(
                id=4000,
                provider="phabricator",
                provider_id=1111,
                head_changeset="1" * 40,
                head_repository=self.repo,
            )
            mock_now.return_value = datetime.fromisoformat("2000-01-01:10")
            self.old_revision = self.repo.base_revisions.create(
                id=4001,
                provider="phabricator",
                provider_id=2222,
                head_changeset="2" * 40,
                head_repository=self.repo,
            )

        self.err_issue = Issue.objects.create(
            path="some/file",
            level=LEVEL_ERROR,
            hash="issue_err",
            analyzer="analyzer-x",
            analyzer_check="check-x",
            message="Some error",
        )
        self.warn_issue = Issue.objects.create(
            path="some/other/file", level=LEVEL_WARNING, hash="issue_warn"
        )

        self.err_link = self.revision.issue_links.create(issue=self.err_issue, line=12)
        self.warn_link = self.revision.issue_links.create(
            issue=self.warn_issue, line=12
        )
        # The same issue (i.e. the same content) is found at another position
        self.revision.issue_links.create(
            issue=self.warn_issue, line=42, nb_lines=2, char=3
        )
        self.old_revision.issue_links.create(issue=self.warn_issue, line=10)

    def serialize_issue(self, issue):
        return {
            "id": str(issue.id),
            "level": issue.level,
            "line": issue.line,
            "path": issue.path,
            "analyzer": issue.analyzer,
            # Use default values
            "char": None,
            "check": None,
            "hash": "",
            "message": None,
            "nb_lines": None,
        }

    def repository_issue(self, issue, positions):
        return {
            "id": str(issue.id),
            "hash": issue.hash,
            "analyzer": issue.analyzer,
            "path": issue.path,
            "level": issue.level,
            "check": issue.analyzer_check,
            "message": issue.message,
            "positions": [
                {"line": line, "nb_lines": nb_lines, "char": char}
                for line, nb_lines, char in positions
            ],
        }

    def test_publishable(self):
        # A warning is not publishable
        self.assertFalse(self.warn_link.publishable)
        # An error is publishable
        self.assertTrue(self.err_link.publishable)

        # A warning in a patch is publishable
        self.warn_link.in_patch = True
        self.assertTrue(self.warn_link.publishable)

        # An error in a patch is publishable
        self.err_link.in_patch = True
        self.assertTrue(self.err_link.publishable)

    def test_list_repository_issues_wrong_values(self):
        """
        A HTTP error 400 is raised when fields are set incorrectly
        """
        with self.assertNumQueries(1):
            response = self.client.get(
                reverse("repository-issues", kwargs={"repo_slug": "no"})
                + "?date=2000-01-01T00:00:00Z&path=.&revision_changeset=whatisthat"
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json(),
            {
                "repo_slug": [
                    "invalid repo_slug path argument - No repository match this slug"
                ],
                "date": ["invalid date - should be YYYY-MM-DD"],
                "revision_changeset": [
                    "invalid revision_changeset - should be the mercurial hash on the head repository"
                ],
            },
        )

    def test_list_repository_issues(self):
        with self.assertNumQueries(4):
            response = self.client.get(
                reverse("repository-issues", kwargs={"repo_slug": "repo_slug"})
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                "count": 2,
                "next": None,
                "previous": None,
                "results": [
                    self.repository_issue(self.err_issue, [(12, None, None)]),
                    # Without a revision filter, positions of all the revisions are listed
                    self.repository_issue(
                        self.warn_issue,
                        [(10, None, None), (12, None, None), (42, 2, 3)],
                    ),
                ],
            },
        )

    def test_list_repository_issues_revision_filter(self):
        """
        Primarily filter issues depending on an existing revision
        """
        with self.assertNumQueries(6):
            response = self.client.get(
                reverse("repository-issues", kwargs={"repo_slug": "repo_slug"})
                + "?date=1999-01-01&revision_changeset="
                + "2" * 40
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(
            data["results"],
            [
                # Only positions on the selected revision are listed
                self.repository_issue(self.warn_issue, [(10, None, None)]),
            ],
        )

    def test_list_repository_issues_date_fallback(self):
        """
        Fall back to the date when no issue match the given revision
        """
        with self.assertNumQueries(6):
            response = self.client.get(
                reverse("repository-issues", kwargs={"repo_slug": "repo_slug"})
                + "?date=2000-01-02&revision_changeset="
                + "A" * 40
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(
            data["results"],
            [
                self.repository_issue(self.warn_issue, [(10, None, None)]),
            ],
        )

    def test_list_repository_issues_date_only(self):
        with self.assertNumQueries(5):
            response = self.client.get(
                reverse("repository-issues", kwargs={"repo_slug": "repo_slug"})
                + "?date=2010-01-01"
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                "count": 2,
                "next": None,
                "previous": None,
                "results": [
                    self.repository_issue(self.err_issue, [(12, None, None)]),
                    self.repository_issue(
                        self.warn_issue, [(12, None, None), (42, 2, 3)]
                    ),
                ],
            },
        )

    def test_list_repository_issues_wrong_revision_no_date(self):
        """
        An empty result is returned when no revision is matched and no date is set
        """
        with self.assertNumQueries(2):
            response = self.client.get(
                reverse("repository-issues", kwargs={"repo_slug": "repo_slug"})
                + "?revision_changeset="
                + "A" * 40
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["results"], [])

    def test_list_repository_issues_date_no_match(self):
        """
        No revision may be found for the date fallback
        """
        with self.assertNumQueries(3):
            response = self.client.get(
                reverse("repository-issues", kwargs={"repo_slug": "repo_slug"})
                + "?date=1999-01-01&revision_changeset="
                + "A" * 40
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["results"], [])
