# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from datetime import datetime
from datetime import timedelta

from django.core.management.base import BaseCommand

from code_review_backend.issues.models import Issue

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
        clean_until = datetime.today() - timedelta(days=options["nb_days"])
        to_delete = Issue.objects.filter(
            diff__repository__slug__in=["autoland", "mozilla-central"],
            created__lte=clean_until,
        )

        count = to_delete.count()
        if not count:
            logger.info("Didn't find any old issue to delete.")
            return

        logger.info(
            f"Retrieved {count} old issues from either autoland or mozilla-central to be deleted."
        )
        to_delete.delete()
        logger.info("Deleted all selected old issues.")
