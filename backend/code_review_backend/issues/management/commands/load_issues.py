# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import logging
import os
import tempfile

import taskcluster
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction

from code_review_backend.issues.compare import detect_new_for_revision
from code_review_backend.issues.models import Issue
from code_review_backend.issues.models import Repository

logger = logging.getLogger(__name__)

INDEX_PATH = "project.relman.{environment}.code-review.phabricator.diff"


class Command(BaseCommand):
    help = "Load issues from remote taskcluster reports"

    def add_arguments(self, parser):
        parser.add_argument(
            "--offline",
            action="store_true",
            default=False,
            help="Use only previously downloaded reports",
        )
        parser.add_argument(
            "-e",
            "--environment",
            default="production",
            choices=("production", "testing"),
            help="Specify the environment to load issues from",
        )

    def handle(self, *args, **options):
        # Check repositories
        for repo in ("mozilla-central", "nss"):
            try:
                Repository.objects.get(slug=repo)
            except Repository.DoesNotExist:
                raise CommandError(f"Missing repository {repo}")

        # Setup cache dir
        self.cache_dir = os.path.join(
            tempfile.gettempdir(), "code-review-reports", options["environment"]
        )
        os.makedirs(self.cache_dir, exist_ok=True)

        # Load available tasks from Taskcluster or already downloaded
        tasks = (
            self.load_local_reports()
            if options["offline"]
            else self.load_tasks(options["environment"])
        )

        for task_id, report in tasks:

            # Build revision & diff
            revision, diff = self.build_revision_and_diff(report["revision"], task_id)

            # Save all issues in a single db transaction
            try:
                issues = self.save_issues(diff, report["issues"])
                logger.info(f"Imported task {task_id} - {len(issues)}")
            except Exception as e:
                logger.error(f"Failed to save issues for {task_id}: {e}")

    @transaction.atomic
    def save_issues(self, diff, issues):
        # Remove all issues from diff
        diff.issues.all().delete()

        # Build all issues for that diff, in a single DB call
        return Issue.objects.bulk_create(
            Issue(
                diff=diff,
                path=i["path"],
                line=i["line"],
                nb_lines=i.get("nb_lines", 1),
                char=i.get("char"),
                level=i.get("level", "warning"),
                check=i.get("kind") or i.get("check"),
                message=i.get("message"),
                analyzer=i["analyzer"],
                hash=i["hash"],
                new_for_revision=detect_new_for_revision(
                    diff, path=i["path"], hash=i["hash"]
                ),
            )
            for i in issues
        )

    def load_tasks(self, environment, chunk=200):
        # Direct unauthenticated usage
        index = taskcluster.Index(
            {"rootUrl": "https://firefox-ci-tc.services.mozilla.com/"}
        )
        queue = taskcluster.Queue(
            {"rootUrl": "https://firefox-ci-tc.services.mozilla.com/"}
        )

        token = None
        while True:

            query = {"limit": chunk}
            if token is not None:
                query["continuationToken"] = token
            data = index.listTasks(
                INDEX_PATH.format(environment=environment), query=query
            )

            for task in data["tasks"]:

                if not task["data"].get("issues"):
                    continue

                # Lookup artifact in cache
                path = os.path.join(self.cache_dir, task["taskId"])
                if os.path.exists(path):
                    artifact = json.load(open(path))

                else:

                    # Download the task report
                    logging.info(f"Download task {task['taskId']}")
                    try:
                        artifact = queue.getLatestArtifact(
                            task["taskId"], "public/results/report.json"
                        )
                    except taskcluster.exceptions.TaskclusterRestFailure as e:
                        if e.status_code == 404:
                            logging.info("Missing artifact")
                            continue
                        raise

                    # Check the artifact has repositories & revision
                    revision = artifact["revision"]
                    assert "repository" in revision, "Missing repository"
                    assert "target_repository" in revision, "Missing target_repository"
                    assert (
                        "mercurial_revision" in revision
                    ), "Missing mercurial_revision"

                    # Store artifact in cache
                    with open(path, "w") as f:
                        json.dump(artifact, f, sort_keys=True, indent=4)

                yield task["taskId"], artifact

            token = data.get("continuationToken")
            if token is None:
                break

    def load_local_reports(self):
        for task_id in os.listdir(self.cache_dir):
            report = json.load(open(os.path.join(self.cache_dir, task_id)))
            yield task_id, report

    def build_revision_and_diff(self, data, task_id):
        """Build or retrieve a revision and diff in current repo from report's data"""
        repository = Repository.objects.get(slug=data["target_repository"])
        revision, _ = repository.revisions.get_or_create(
            id=data["id"],
            defaults={
                "phid": data["phid"],
                "title": data["title"],
                "bugzilla_id": int(data["bugzilla_id"])
                if data["bugzilla_id"]
                else None,
            },
        )
        diff, _ = revision.diffs.get_or_create(
            id=data["diff_id"],
            defaults={
                "phid": data["diff_phid"],
                "review_task_id": task_id,
                "mercurial_hash": data["mercurial_revision"],
            },
        )
        return revision, diff
