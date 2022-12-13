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
from django.db import transaction
from requests.exceptions import HTTPError

from code_review_backend.issues.compare import detect_new_for_revision
from code_review_backend.issues.models import Issue
from code_review_backend.issues.models import IssueLink
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
            if not revision:
                continue

            # Save all issues in a single db transaction
            try:
                issues = self.save_issues(diff, report["issues"])
                logger.info(f"Imported task {task_id} - {len(issues)}")
            except Exception as e:
                logger.error(f"Failed to save issues for {task_id}: {e}", exc_info=True)

    @transaction.atomic
    def save_issues(self, diff, issues):
        # Remove all issues from diff
        diff.issues.all().delete()

        # Build all issues for that diff, in a single DB call
        created_issues = Issue.objects.bulk_create(
            Issue(
                path=i["path"],
                line=i["line"],
                nb_lines=i.get("nb_lines", 1),
                char=i.get("char"),
                level=i.get("level", "warning"),
                analyzer_check=i.get("kind") or i.get("check"),
                message=i.get("message"),
                analyzer=i["analyzer"],
                hash=i["hash"],
                new_for_revision=detect_new_for_revision(
                    diff, path=i["path"], hash=i["hash"]
                ),
            )
            for i in issues
        )
        IssueLink.objects.bulk_create(
            IssueLink(
                issue=i,
                diff=diff,
                revision_id=diff.revision_id,
            )
            for i in created_issues
        )
        return created_issues

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
                        url = queue.buildUrl(
                            "getLatestArtifact",
                            task["taskId"],
                            "public/results/report.json",
                        )
                        # Allows HTTP_30x redirections retrieving the artifact
                        response = queue.session.get(
                            url, stream=True, allow_redirects=True
                        )
                        response.raise_for_status()
                        artifact = response.json()
                    except HTTPError as e:
                        if (
                            getattr(getattr(e, "response", None), "status_code", None)
                            == 404
                        ):
                            logging.info(f"Missing artifact : {repr(e)}")
                            continue
                        raise e

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
        try:
            repository = Repository.objects.get(url=data["target_repository"])
        except Repository.DoesNotExist:
            logger.warning(
                "No repository found with URL {data['repository']}, skipping."
            )
            return None, None
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
            repository=repository,
            defaults={
                "repository": repository,
                "phid": data["diff_phid"],
                "review_task_id": task_id,
                "mercurial_hash": data["mercurial_revision"],
            },
        )
        return revision, diff
