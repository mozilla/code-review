# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import math
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from code_review_backend.issues.models import Diff, Issue, IssueLink, Revision

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

DEL_CHUNK_SIZE = 1000


class Command(BaseCommand):
    help = "Cleanup old issues from autoland and mozilla-central repositories"

    def add_arguments(self, parser):
        parser.add_argument(
            "--nb-days",
            type=int,
            help="Number of days the issues are old to select them for cleaning, defaults to 30 days (1 month)",
            default=30,
        )

    def handle(self, *args, **options):
        clean_until = timezone.now() - timedelta(days=options["nb_days"])

        rev_to_delete = Revision.objects.filter(
            base_repository__slug__in=["autoland", "mozilla-central"],
            head_repository__slug__in=["autoland", "mozilla-central"],
            created__lte=clean_until,
        )
        count_rev = rev_to_delete.count()

        if not count_rev:
            logger.info("Didn't find any old revision to delete.")
            return

        logger.info(
            f"Retrieved {count_rev} old revisions from either autoland or mozilla-central to be deleted."
        )

        stats = {}

        iterations = math.ceil(count_rev / DEL_CHUNK_SIZE)
        i = 0
        for i, start in enumerate(range(0, count_rev, DEL_CHUNK_SIZE), start=1):
            logger.info(f"Page {i}/{iterations}.")
            # First fetch revisions IDs in a first DB request
            chunk_rev_ids = rev_to_delete.order_by("id")[
                start : start + DEL_CHUNK_SIZE
            ].values_list("id", flat=True)

            # Delete IssueLink for this chunk
            links_qs = IssueLink.objects.filter(revision_id__in=chunk_rev_ids)
            # Store IDs of related Issues, to make issues deletion faster later on
            chunk_issues_ids = Issue.objects.filter(
                issue_link__revision_id__in=chunk_rev_ids
            ).values_list("id", flat=True)
            _, links_stats = links_qs.delete()
            stats.update(links_stats)

            # Delete Diff for this chunk
            _, diffs_stats = Diff.objects.filter(
                revision__id__in=chunk_rev_ids
            ).delete()
            stats.update(diffs_stats)

            # Delete issues that are not linked to a revision anymore
            issues_qs = Issue.objects.filter(
                id__in=chunk_issues_ids,
                issue_links=None,
            )
            # Perform a raw deletion to avoid Django performing lookups to IssueLink
            # as the M2M has already be cleaned up at this stage.
            issues_count = issues_qs._raw_delete(issues_qs.db)
            stats.update(issues_count)

        # Drop the revisions
        _, rev_stats = rev_to_delete.delete()
        stats.update(rev_stats)

        msg = ", ".join((f"{n} {key}" for key, n in stats.items()))
        logger.info(f"Deleted {msg}.")
