# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import uuid
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from code_review_backend.issues.models import LEVEL_ERROR
from code_review_backend.issues.models import Issue
from code_review_backend.issues.models import Repository

UUID_PATTERN = "********-****-****-****-************"
LOG_PREFIX = "INFO:code_review_backend.issues.management.commands.cleanup_issues:"


class CleanupIssuesCommandTestCase(TestCase):
    def setUp(self):
        super().setUp()

        today = timezone.now()
        dates = [
            today - timedelta(days=35),
            today - timedelta(days=5),
            today - timedelta(days=1),
        ]

        repos = Repository.objects.bulk_create(
            [
                Repository(id=i, slug=slug, url=f"https://www.test-{slug}.com")
                for i, slug in enumerate(["mozilla-central", "autoland", "whatever"])
            ]
        )

        issue_ids = 0
        for i, repo in enumerate(repos):
            rev = repo.revisions.create(
                id=i, phid=i, title=f"Revision {i} for repo {repo}"
            )
            diff = rev.diffs.create(
                id=i, phid=i, review_task_id=i, mercurial_hash=i, repository=repo
            )
            issues = Issue.objects.bulk_create(
                [
                    Issue(
                        id=UUID_PATTERN.replace("*", str(issue_ids + j)),
                        path=f"somepath/{issue_ids + j}.issue",
                        level=LEVEL_ERROR,
                        analyzer=f"test-diff-{diff.id}",
                        hash=f"HASH-{issue_ids + j}",
                        diff=diff,
                    )
                    for j in range(3)
                ]
            )

            for index, issue in enumerate(issues):
                issue.created = dates[index]
                issue.save(update_fields=["created"])

            issue_ids += 3

    def test_cleanup_issues_no_issue(self):
        with self.assertLogs() as mock_log:
            with self.assertNumQueries(1):
                call_command("cleanup_issues", "--nb-days", "40")

        self.assertEqual(
            mock_log.output,
            [
                f"{LOG_PREFIX}Didn't find any old issue to delete.",
            ],
        )

    def test_cleanup_issues_default_nb_days(self):
        self.assertEqual(Issue.objects.count(), 9)
        with self.assertLogs() as mock_log:
            with self.assertNumQueries(2):
                call_command(
                    "cleanup_issues",
                )

        self.assertEqual(Issue.objects.count(), 7)
        self.assertListEqual(
            list(Issue.objects.all().values_list("id", flat=True)),
            [
                uuid.UUID(
                    "11111111-1111-1111-1111-111111111111"
                ),  # on mozilla-central, but too recent
                uuid.UUID(
                    "22222222-2222-2222-2222-222222222222"
                ),  # on mozilla-central, but too recent
                uuid.UUID(
                    "44444444-4444-4444-4444-444444444444"
                ),  # on autoland, but too recent
                uuid.UUID(
                    "55555555-5555-5555-5555-555555555555"
                ),  # on autoland, but too recent
                uuid.UUID(
                    "66666666-6666-6666-6666-666666666666"
                ),  # on whatever (unhandled repo)
                uuid.UUID(
                    "77777777-7777-7777-7777-777777777777"
                ),  # on whatever (unhandled repo)
                uuid.UUID(
                    "88888888-8888-8888-8888-888888888888"
                ),  # on whatever (unhandled repo)
            ],
        )

        self.assertListEqual(
            mock_log.output,
            [
                f"{LOG_PREFIX}Retrieved 2 old issues from either autoland or mozilla-central to be deleted.",
                f"{LOG_PREFIX}Deleted all selected old issues.",
            ],
        )

    def test_cleanup_issues_custom_nb_days(self):
        self.assertEqual(Issue.objects.count(), 9)
        with self.assertLogs() as mock_log:
            with self.assertNumQueries(2):
                call_command("cleanup_issues", "--nb-days", "4")

        self.assertEqual(Issue.objects.count(), 5)
        self.assertListEqual(
            list(Issue.objects.all().values_list("id", flat=True)),
            [
                uuid.UUID(
                    "22222222-2222-2222-2222-222222222222"
                ),  # on mozilla-central, but too recent
                uuid.UUID(
                    "55555555-5555-5555-5555-555555555555"
                ),  # on autoland, but too recent
                uuid.UUID(
                    "66666666-6666-6666-6666-666666666666"
                ),  # on whatever (unhandled repo)
                uuid.UUID(
                    "77777777-7777-7777-7777-777777777777"
                ),  # on whatever (unhandled repo)
                uuid.UUID(
                    "88888888-8888-8888-8888-888888888888"
                ),  # on whatever (unhandled repo)
            ],
        )

        self.assertEqual(
            mock_log.output,
            [
                f"{LOG_PREFIX}Retrieved 4 old issues from either autoland or mozilla-central to be deleted.",
                f"{LOG_PREFIX}Deleted all selected old issues.",
            ],
        )
