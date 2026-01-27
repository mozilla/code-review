# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import hashlib
import random

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from code_review_backend.issues.compare import detect_new_for_revision
from code_review_backend.issues.models import Diff, Issue, Repository


class CompareAPITestCase(APITestCase):
    def setUp(self):
        # Create a user
        self.user = User.objects.create(username="crash_user")

        # Create a repo & its try counterpart
        self.repo = Repository.objects.create(
            id=1, slug="myrepo", url="http://repo.test/myrepo"
        )
        self.repo_try = Repository.objects.create(
            id=2, slug="myrepo-try", url="http://repo.test/try"
        )

        # Create a simple stack with 2 diffs
        self.revision = self.repo_try.head_revisions.create(
            provider="phabricator",
            provider_id=1,
            title="Revision XYZ",
            bugzilla_id=1234567,
            base_repository=self.repo,
        )
        for i in range(2):
            self.revision.diffs.create(
                id=i + 1,
                provider_id=f"PHID-DIFF-{i+1}",
                review_task_id=f"task-{i}",
                mercurial_hash=hashlib.sha1(f"hg {i}".encode()).hexdigest(),
                repository=self.repo_try,
            )

        # Add 3 issues on first diff
        for i in range(3):
            self.build_issue(1, i)

    def build_issue(self, diff_id, hash_id):
        issue, _ = Issue.objects.get_or_create(
            hash=self.build_hash(hash_id),
            defaults={
                "path": "path/to/file",
                "level": "warning",
                "message": None,
                "analyzer": "analyzer-x",
                "analyzer_check": "check-y",
            },
        )
        # Link the issue to the specific diff
        issue.issue_links.create(
            diff_id=diff_id,
            revision=self.revision,
            line=random.randint(1, 100),
            nb_lines=random.randint(1, 100),
            char=None,
        )
        return issue

    def build_hash(self, content):
        """Produce a dummy hash from some content"""
        return hashlib.md5(bytes(content)).hexdigest()

    def test_detect_new_for_revision(self):
        """
        Check the detection of a new issue in a revision
        """
        # No issues on second diff at first
        self.assertFalse(Issue.objects.filter(diffs=2).exists())

        # All issues on top diff are new
        top_diff = Diff.objects.get(pk=1)
        for issue in top_diff.issues.all():
            self.assertTrue(detect_new_for_revision(top_diff, issue.path, issue.hash))

        # Adding an issue with same hash on second diff will be set as existing
        second_diff = Diff.objects.get(pk=2)
        issue = self.build_issue(2, 1)
        self.assertFalse(detect_new_for_revision(second_diff, issue.path, issue.hash))

        # But adding an issue with a different hash on second diff will be set as new
        issue = self.build_issue(2, 12345)
        self.assertTrue(detect_new_for_revision(second_diff, issue.path, issue.hash))
