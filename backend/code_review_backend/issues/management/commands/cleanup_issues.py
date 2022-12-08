# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from code_review_backend.issues.models import Issue
from code_review_backend.issues.models import Revision

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


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
            repository__slug__in=["autoland", "mozilla-central"],
            created__lte=clean_until,
        )

        count = rev_to_delete.count()
        if not count:
            logger.info("Didn't find any old revision to delete.")
            return

        # Delete revisions, with their related IssueLink and Diff
        logger.info(
            f"Retrieved {count} old revisions from either autoland or mozilla-central to be deleted."
        )
        _, stats = rev_to_delete.delete()
        # Delete issues that are not linked to a revision anymore
        _, issues_stats = Issue.objects.filter(revisions__isnull=True).delete()
        stats.update(issues_stats)
        msg = ", ".join((f"{n} {key}" for key, n in stats.items()))
        logger.info(f"Deleted {msg}.")
