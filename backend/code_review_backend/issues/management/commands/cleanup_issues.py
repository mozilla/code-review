# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import math
from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from code_review_backend.issues.models import (
    Diff,
    Issue,
    IssueLink,
    Repository,
    Revision,
)

logger = logging.getLogger(__name__)

DEL_CHUNK_SIZE = 500


class Command(BaseCommand):
    help = "Cleanup old issues from all repositories"

    def add_arguments(self, parser):
        parser.add_argument(
            "--nb-days",
            type=int,
            help="Number of days the issues are old to select them for cleaning, defaults to 30 days (1 month)",
            default=30,
        )

    def cleanup_repositories(self):
        unused_repositories = Repository.objects.filter(
            base_revisions__isnull=True,
            head_revisions__isnull=True,
            diffs__isnull=True,
        )
        return unused_repositories._raw_delete(unused_repositories.db)

    def handle(self, *args, **options):
        stats = defaultdict(int)
        repo_count = self.cleanup_repositories()
        if repo_count:
            stats["Repository"] = repo_count

        clean_until = timezone.now() - timedelta(days=options["nb_days"])

        rev_to_delete = Revision.objects.filter(
            created__lte=clean_until,
        )
        total_rev_count = rev_to_delete.count()

        if not total_rev_count:
            logger.info("Didn't find any old revision to delete.")
            return

        logger.info(f"Retrieved {total_rev_count} old revisions to be deleted.")

        iterations = math.ceil(total_rev_count / DEL_CHUNK_SIZE)
        for i, start in enumerate(range(0, total_rev_count, DEL_CHUNK_SIZE), start=1):
            logger.info(f"Page {i}/{iterations}.")
            # First fetch revisions IDs in a first DB request
            chunk_rev_ids = rev_to_delete.order_by("id")[
                start : start + DEL_CHUNK_SIZE
            ].values_list("id", flat=True)

            # Store IDs of related Issues, to make issues deletion faster later on
            chunk_issues_ids = list(
                Issue.objects.filter(
                    issue_links__revision_id__in=chunk_rev_ids
                ).values_list("id", flat=True)
            )

            # Delete IssueLink for this chunk
            links_qs = IssueLink.objects.filter(revision_id__in=chunk_rev_ids)
            links_count = links_qs._raw_delete(links_qs.db)
            stats["IssueLink"] += links_count

            # Perform a raw deletion to avoid Django performing lookups to IssueLink
            # as the M2M has already be cleaned up at this stage.
            diffs_qs = Diff.objects.filter(revision__id__in=chunk_rev_ids)
            diffs_count = diffs_qs._raw_delete(diffs_qs.db)
            stats["Diff"] += diffs_count

            # Only delete issues that are not linked to a revision anymore
            issues_qs = Issue.objects.filter(
                id__in=chunk_issues_ids,
                issue_links=None,
            )
            # Perform a raw deletion to avoid Django performing lookups to IssueLink
            # as the M2M has already be cleaned up at this stage.
            issues_count = issues_qs._raw_delete(issues_qs.db)
            stats["Issue"] += issues_count

        # Drop the revisions with a raw deletion to avoid Django performing lookups to IssueLink
        # as the M2M has already be cleaned up at this stage.
        rev_count = rev_to_delete._raw_delete(rev_to_delete.db)
        stats["Revision"] += rev_count

        msg = ", ".join((f"{n} {key}" for key, n in stats.items()))
        logger.info(f"Deleted {msg}.")
