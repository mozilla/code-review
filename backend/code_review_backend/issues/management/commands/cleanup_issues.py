# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from code_review_backend.issues.models import Diff, Issue, IssueLink, Revision

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

DEL_CHUNK_SIZE = 10000
UPDATE_CHUNK_SIZE = 10000


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

        # For issue and issuelink we can use _raw_delete since it's faster and doesn't
        # give OOM since there are no CASCADE directives in the model since django
        # doesn't need to query the model and compute the dependencies.
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
        for start in range(0, count_rev, DEL_CHUNK_SIZE):
            # First fetch revisions IDs in a first DB request
            chunk_rev_ids = rev_to_delete.order_by("id")[
                start : start + UPDATE_CHUNK_SIZE
            ].values_list("id", flat=True)
            # Delete IssueLink for this chunk
            _, links_stats = IssueLink.objects.filter(
                revision_id__in=chunk_rev_ids
            ).delete()
            stats.update(links_stats)
            # Delete Diff for this chunk
            _, diffs_stats = Diff.objects.filter(
                revision__id__in=chunk_rev_ids
            ).delete()
            stats.update(diffs_stats)

        # Drop the revisions
        _, rev_stats = rev_to_delete.delete()
        stats.update(rev_stats)

        # Finally, delete issues that are not linked to any revision anymore
        _, issues_count = Issue.objects.filter(issue_links=None).delete()
        stats.update(issues_count)

        msg = ", ".join((f"{n} {key}" for key, n in stats.items()))
        logger.info(f"Deleted {msg}.")
