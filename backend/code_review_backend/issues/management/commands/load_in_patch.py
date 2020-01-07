# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
from multiprocessing import Pool

import requests
from django.core.management.base import BaseCommand
from parsepatch.patch import Patch

from code_review_backend.issues.models import Diff
from code_review_backend.issues.models import Issue

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


def load_hgmo_patch(diff):
    # Load the parent info as we have the try-task-config commit
    url = f"{diff.repository.url}/json-rev/{diff.mercurial_hash}"
    logging.info(f"Downloading {url}")
    resp = requests.get(url)
    resp.raise_for_status()
    meta = resp.json()
    if meta["desc"].startswith("try_task_config"):
        patch_rev = resp.json()["parents"][0]
    else:
        patch_rev = diff.mercurial_hash

    # Load the parent patch
    url = f"{diff.repository.url}/raw-rev/{patch_rev}"
    logging.info(f"Downloading {url}")
    resp = requests.get(url)
    resp.raise_for_status()

    patch = Patch.parse_patch(resp.content.decode("utf-8"), skip_comments=False)
    assert patch != {}, "Empty patch"
    lines = {
        # Use all changes in new files
        filename: diff.get("touched", []) + diff.get("added", [])
        for filename, diff in patch.items()
    }

    return lines


def detect_in_patch(issue, lines):
    """From the code-review bot revisions.py contains() method"""
    modified_lines = lines.get(issue.path)

    if modified_lines is None:
        # File not in patch
        issue.in_patch = False

    elif issue.line is None:
        # Empty line means full file
        issue.in_patch = True

    else:
        # Detect if this issue is in the patch
        chunk_lines = set(range(issue.line, issue.line + issue.nb_lines))
        issue.in_patch = not chunk_lines.isdisjoint(modified_lines)
    return issue


def process_diff(diff: Diff):
    """This function needs to be on the top level in order to be usable by the pool"""
    try:
        lines = load_hgmo_patch(diff)

        issues = [detect_in_patch(issue, lines) for issue in diff.issues.all()]
        logging.info(
            "Found {} issues in patch for {}".format(
                len([i for i in issues if i.in_patch]), diff.id
            )
        )
        Issue.objects.bulk_update(issues, ["in_patch"])
    except Exception as e:
        logging.info(f"Failure on diff {diff.id}: {e}")


class Command(BaseCommand):
    help = "Load issues from remote taskcluster reports"

    def add_arguments(self, parser):
        parser.add_argument(
            "--nb-processes",
            type=int,
            help="Number of processes used to process the diffs",
            default=1,
        )

    def handle(self, *args, **options):
        # Only apply on diffs with issues that are not already processed
        diffs = (
            Diff.objects.filter(issues__in_patch__isnull=True).order_by("id").distinct()
        )
        logger.info("Will process {} diffs".format(diffs.count()))

        # Process all the diffs in parallel
        with Pool(processes=options["nb_processes"]) as pool:
            pool.map(process_diff, diffs, chunksize=20)
