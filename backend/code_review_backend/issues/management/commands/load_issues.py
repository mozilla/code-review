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

from code_review_backend.issues.models import Issue
from code_review_backend.issues.models import Repository

logger = logging.getLogger(__name__)

INDEX_PATH = "project.relman.production.code-review.phabricator.diff"


class Command(BaseCommand):
    help = "Load issues from remote taskcluster reports"

    def add_arguments(self, parser):
        parser.add_argument(
            "--offline",
            action="store_true",
            default=False,
            help="Use only previously downloaded reports",
        )

    def handle(self, *args, **options):
        # Check repositories
        for repo in ("mozilla-central", "nss"):
            try:
                Repository.objects.get(slug=repo)
            except Repository.DoesNotExist:
                raise CommandError(f"Missing repository {repo}")

        # Setup cache dir
        self.cache_dir = os.path.join(tempfile.gettempdir(), "code-review-reports")
        os.makedirs(self.cache_dir, exist_ok=True)

        # Load available tasks from Taskcluster or already downloaded
        tasks = self.load_local_reports() if options["offline"] else self.load_tasks()

        for task_id, report in tasks:

            # Build revision & diff
            revision, diff = self.build_hierarchy(report["revision"], task_id)

            with transaction.atomic():
                # Remove all issues from diff
                diff.issues.all().delete()

                # Build all issues for that diff, in a single DB call
                issues = Issue.objects.bulk_create(
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
                    )
                    for i in report["issues"]
                )
                print(task_id, len(issues))

                for issue in issues:
                    issue.hash = issue.build_hash()
                    issue.save()

    def load_tasks(self, chunk=200):
        # Direct unauthenticated usage
        index = taskcluster.Index({"rootUrl": "https://taskcluster.net"})
        queue = taskcluster.Queue({"rootUrl": "https://taskcluster.net"})

        token = None
        while True:

            query = {"limit": chunk}
            if token is not None:
                query["continuationToken"] = token
            data = index.listTasks(INDEX_PATH, query=query)

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
                            logging.info(f"Missing artifact")
                            continue
                        raise

                    # Load the task definition of the main task in group
                    # to get the mercurial revision of the patch
                    # It should always be the decision task that has mercurial refs
                    decision_task = queue.task(task["data"]["try_group_id"])
                    decision_env = decision_task["payload"].get("env", {})
                    if "GECKO_HEAD_REV" in decision_env:
                        # mozilla-central rev
                        repo_slug = "mozilla-central"
                        repo_rev = decision_env["GECKO_HEAD_REV"]

                    elif "NSS_HEAD_REVISION" in decision_env:
                        # nss rev
                        repo_slug = "nss"
                        repo_rev = decision_env["NSS_HEAD_REVISION"]
                    else:
                        raise Exception(
                            f"Missing gecko rev in task {task['data']['try_group_id']}"
                        )

                    # Add missing data in artifact
                    artifact["revision"]["mercurial"] = repo_rev
                    artifact["revision"]["repository"] = repo_slug

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

    def build_hierarchy(self, data, task_id):
        """Build or retrieve a revision and diff in current repo from report's data"""
        repository = Repository.objects.get(slug=data["repository"])
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
                "mercurial": data["mercurial"],
            },
        )
        return revision, diff
