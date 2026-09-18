from rest_framework import status
from rest_framework.test import APITestCase

from code_review_backend.issues.models import Issue, Repository


class ListIssuesTestCase(APITestCase):
    def setUp(self):
        # Create the main repository
        self.repo_main = Repository.objects.create(
            slug="mozilla-central", url="https://hg.mozilla.org/mozilla-central"
        )
        self.repo_try = Repository.objects.create(
            slug="myrepo-try", url="http://repo.test/try"
        )

        self.issues = Issue.objects.bulk_create(
            [
                Issue(**attrs)
                for attrs in [
                    {"hash": "0" * 32},
                    {"hash": "1" * 32},
                    {"hash": "2" * 32},
                    {"hash": "3" * 32},
                ]
            ]
        )

        # Create historic revision with some issues
        self.revision_main = self.repo_main.head_revisions.create(
            phabricator_id=456,
            phabricator_phid="PHID-REV-XXX",
            title="Main revision",
            base_repository=self.repo_main,
            head_repository=self.repo_main,
        )
        self.revision_main.issue_links.create(issue=self.issues[0])
        self.revision_main.issue_links.create(issue=self.issues[1])

        # Create a new revions, with two successive diffs
        self.revision_last = self.repo_try.head_revisions.create(
            phabricator_id=1337,
            phabricator_phid="PHID-REV-YYY",
            title="Bug XXX - Yet another bug",
            base_repository=self.repo_main,
            head_repository=self.repo_try,
        )
        self.diff1 = self.revision_last.diffs.create(
            id=1,
            repository=self.repo_try,
            review_task_id="deadbeef123",
            phid="PHID-DIFF-xxx",
        )
        self.diff1.issue_links.create(revision=self.revision_last, issue=self.issues[0])
        self.diff1.issue_links.create(revision=self.revision_last, issue=self.issues[2])
        self.diff1.issue_links.create(revision=self.revision_last, issue=self.issues[3])

        self.diff2 = self.revision_last.diffs.create(
            id=2,
            repository=self.repo_try,
            review_task_id="coffee12345",
            phid="PHID-DIFF-yyy",
        )
        self.diff2.issue_links.create(revision=self.revision_last, issue=self.issues[0])
        self.diff2.issue_links.create(revision=self.revision_last, issue=self.issues[2])

    def test_list_issues_invalid_mode(self):
        with self.assertNumQueries(0):
            response = self.client.get(
                f"/v2/diff/{self.diff2.id}/issues/test/", format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertListEqual(
            response.json(),
            ["mode argument must be one of ['unresolved', 'known', 'closed']"],
        )

    def test_list_issues_invalid_diff(self):
        with self.assertNumQueries(1):
            response = self.client.get("/v2/diff/424242/issues/known/")
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_issues_known(self):
        with self.assertNumQueries(2):
            response = self.client.get(f"/v2/diff/{self.diff2.id}/issues/known/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.maxDiff = None
        self.assertDictEqual(
            response.json(),
            {
                "previous_diff_id": None,
                "issues": [
                    {"id": str(self.issues[0].id), "hash": self.issues[0].hash},
                ],
            },
        )

    def test_list_issues_unresolved_first_diff(self):
        """No issue can be marked as unresolved on a new diff"""
        with self.assertNumQueries(2):
            response = self.client.get(
                f"/v2/diff/{self.diff1.id}/issues/unresolved/", format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_issues_unresolved(self):
        with self.assertNumQueries(3):
            response = self.client.get(f"/v2/diff/{self.diff2.id}/issues/unresolved/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictEqual(
            response.json(),
            {
                "previous_diff_id": "1",
                "issues": [
                    {"id": str(self.issues[2].id), "hash": self.issues[2].hash},
                ],
            },
        )

    def test_list_issues_closed_first_diff(self):
        """No issue can be marked as closed on a new diff"""
        with self.assertNumQueries(2):
            response = self.client.get(f"/v2/diff/{self.diff1.id}/issues/closed/")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_issues_closed(self):
        with self.assertNumQueries(3):
            response = self.client.get(f"/v2/diff/{self.diff2.id}/issues/closed/")
            self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertDictEqual(
            response.json(),
            {
                "previous_diff_id": "1",
                "issues": [{"id": str(self.issues[3].id), "hash": self.issues[3].hash}],
            },
        )

    def test_list_issues_new_diff_reopen(self):
        """
        Open a new diff with 1 known issue and one that has been closed in the previous diff.
        Both are listed as new, and the two issues of the previous diff listed as closed.
        """
        diff = self.revision_last.diffs.create(
            id=3,
            repository=self.repo_try,
            review_task_id="42",
            phid="PHID-DIFF-42",
        )
        new_issue = Issue.objects.create(hash="4" * 32)
        diff.issue_links.create(revision=self.revision_last, issue=new_issue)
        diff.issue_links.create(revision=self.revision_last, issue=self.issues[3])
        self.assertDictEqual(
            self.client.get(f"/v2/diff/{diff.id}/issues/unresolved/").json(),
            {
                "previous_diff_id": "2",
                "issues": [],
            },
        )
        self.assertDictEqual(
            self.client.get(f"/v2/diff/{diff.id}/issues/known/").json(),
            {
                "previous_diff_id": None,
                "issues": [],
            },
        )
        self.assertDictEqual(
            self.client.get(f"/v2/diff/{diff.id}/issues/closed/").json(),
            {
                "previous_diff_id": "2",
                "issues": [
                    {"id": str(self.issues[0].id), "hash": self.issues[0].hash},
                    {"id": str(self.issues[2].id), "hash": self.issues[2].hash},
                ],
            },
        )
