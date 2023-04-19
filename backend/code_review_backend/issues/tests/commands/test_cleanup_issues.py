# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import uuid
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from code_review_backend.issues.models import (
    LEVEL_ERROR,
    Diff,
    Issue,
    IssueLink,
    Repository,
    Revision,
)

LOG_PREFIX = "INFO:code_review_backend.issues.management.commands.cleanup_issues:"


def build_issue(path, revisions=[]):
    issue, _ = Issue.objects.get_or_create(
        path=path,
        level=LEVEL_ERROR,
        analyzer="analyzer",
        defaults={"hash": uuid.uuid4()},
    )
    for rev in revisions:
        issue.issue_links.create(revision=rev)
    return issue


class CleanupIssuesCommandTestCase(TestCase):
    def setUp(self):
        super().setUp()

        (
            self.moz_central,
            self.autoland,
            self.test_repo,
        ) = Repository.objects.bulk_create(
            [
                Repository(id=i, slug=slug, url=f"https://www.test-{slug}.com")
                for i, slug in enumerate(["mozilla-central", "autoland", "test"])
            ]
        )

        # The first revision is on mozilla-central and has been ingested 35 days ago
        # The second revision is on autoland and has been ingested 15 days ago
        # The third revision is on test and has been ingested 1 days ago
        rev_1, rev_2, rev_3 = Revision.objects.bulk_create(
            [
                Revision(
                    phabricator_id=i,
                    phabricator_phid=i,
                    title=f"Revision {i}",
                    base_repository=repo,
                    head_repository=repo,
                )
                for i, repo in enumerate(
                    (self.moz_central, self.autoland, self.test_repo)
                )
            ]
        )
        for rev, days_ago in ((rev_1, 35), (rev_2, 15), (rev_3, 1)):
            rev.created = timezone.now() - timedelta(days=days_ago)
            rev.save(update_fields=["created"])

        # Two issues are linked to the first revision via a diff
        build_issue("path1", [rev_1])
        build_issue("path2", [rev_1])
        diff = rev_1.diffs.create(
            id=1337,
            review_task_id="Task",
            mercurial_hash="MercurialHash",
            repository=self.moz_central,
        )
        IssueLink.objects.filter(revision=rev_1).update(diff=diff)

        # Two issues are linked to the second revision
        build_issue("path3", [rev_2])
        build_issue("path4", [rev_2])

        # Two issues are linked to both the second and the third revisions
        build_issue("path5", [rev_1, rev_3])
        build_issue("path6", [rev_1, rev_3])

    def test_cleanup_issues_no_issue(self):
        with self.assertLogs() as mock_log:
            with self.assertNumQueries(1):
                call_command("cleanup_issues", "--nb-days", "40")

        self.assertEqual(
            mock_log.output,
            [
                f"{LOG_PREFIX}Didn't find any old revision to delete.",
            ],
        )

    def test_cleanup_issues_default_nb_days(self):
        self.assertEqual(Issue.objects.count(), 6)
        with self.assertLogs() as mock_log:
            with self.assertNumQueries(10):
                call_command(
                    "cleanup_issues",
                )

        self.assertEqual(Issue.objects.count(), 4)
        self.assertListEqual(
            list(Issue.objects.values_list("path", flat=True)),
            ["path3", "path4", "path5", "path6"],
        )

        self.assertFalse(Diff.objects.exists())
        self.assertFalse(self.moz_central.base_revisions.exists())
        self.assertFalse(self.moz_central.head_revisions.exists())

        self.assertListEqual(
            mock_log.output,
            [
                f"{LOG_PREFIX}Retrieved 1 old revisions from either autoland or mozilla-central to be deleted.",
                f"{LOG_PREFIX}Deleted 4 issues.IssueLink, 1 issues.Diff, 1 issues.Revision, 2 issues.Issue.",
            ],
        )

    def test_cleanup_issues_custom_nb_days(self):
        self.assertEqual(Issue.objects.count(), 6)
        with self.assertLogs() as mock_log:
            with self.assertNumQueries(10):
                call_command("cleanup_issues", "--nb-days", "4")

        self.assertEqual(Issue.objects.count(), 2)
        self.assertListEqual(
            list(Issue.objects.values_list("path", flat=True)),
            ["path5", "path6"],
        )

        self.assertEqual(
            mock_log.output,
            [
                f"{LOG_PREFIX}Retrieved 2 old revisions from either autoland or mozilla-central to be deleted.",
                f"{LOG_PREFIX}Deleted 6 issues.IssueLink, 1 issues.Diff, 2 issues.Revision, 4 issues.Issue.",
            ],
        )
