#!/usr/bin/env python
# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import re
import time
from datetime import datetime
from datetime import timedelta

import requests
from taskcluster.helper import TaskclusterConfig

TREEHERDER_PUSH_URL = "https://treeherder.mozilla.org/api/project/try/push/"
TREEHERDER_JOBS_URL = "https://treeherder.mozilla.org/api/jobs/"
TREEHERDER_HEADERS = {"user-agent": "code-review-bot/1.0.0"}
BACKEND_URL = "https://api.code-review.moz.tools/v1/diff/"
REGEX_PHAB_ID = re.compile(
    r"try_task_config for https://phabricator.services.mozilla.com/D(\d+)"
)
PHABRICATOR_REVISION_URL = (
    "https://phabricator.services.mozilla.com/api/differential.revision.search"
)

taskcluster = TaskclusterConfig("https://firefox-ci-tc.services.mozilla.com")


def phab_state(revision_id):
    data = {
        "constraints[ids][0]": revision_id,
        "api.token": taskcluster.secrets["PHABRICATOR"]["api_key"],
    }
    resp = requests.post(PHABRICATOR_REVISION_URL, data)
    resp.raise_for_status()
    data = resp.json()
    return data["result"]["data"][0]["fields"]["status"]


def list_diffs(min_date, max_date):
    url = BACKEND_URL

    revisions = []
    updates = {}

    while True:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()

        for diff in data["results"]:
            # Limit to specific dates
            date = datetime.strptime(diff["created"], "%Y-%m-%dT%H:%M:%S.%fZ")
            if date >= max_date:
                continue
            if date < min_date:
                return revisions, updates

            # Save revision
            revisions.append(diff["mercurial_hash"])

            # Save best date for a Phabricator revision
            last_date = updates.get(diff["revision"]["id"])
            if last_date is None or last_date < date:
                updates[diff["revision"]["id"]] = date

        # Move to next page
        url = data["next"]


def timestamp(date):
    return time.mktime(date.timetuple())


def list_pushes(known_revisions, updates, min_date, max_date):
    params = {
        # 'full': 'true',
        "count": 10,
        "author": "reviewbot",
        "push_timestamp__lte": timestamp(max_date),
    }

    while True:
        resp = requests.get(TREEHERDER_PUSH_URL, params, headers=TREEHERDER_HEADERS)
        resp.raise_for_status()
        data = resp.json()

        for job in data["results"]:
            rev = job["revision"]
            date = datetime.fromtimestamp(job["push_timestamp"])

            if date < min_date:
                return

            # Check if that job has been processed
            if rev in known_revisions:
                print(f"Skipping {rev}: already in backend")
                continue

            # Check if that phabricator revision needs an update
            match = REGEX_PHAB_ID.search(job["revisions"][0]["comments"])
            if match is None:
                print(f"No Phabricator revision found for {rev}")

            phab_revision = int(match.group(1))
            update = updates.get(phab_revision)
            if update and update > date:
                print(f"Skipping {rev}: revision already got a review")
                continue

            # Check if revision is still open
            state = phab_state(phab_revision)
            if state["closed"] is True:
                print(
                    f"Skipping {rev}: revision is closed on Phabricator {phab_revision}"
                )
                continue

            # Process job
            yield job

        # Go to next page
        params["push_timestamp__lte"] = job["push_timestamp"] - 1


def find_task(push_id):
    # Find the task ids from Treeherder
    resp = requests.get(
        TREEHERDER_JOBS_URL, {"push_id": push_id}, headers=TREEHERDER_HEADERS
    )
    resp.raise_for_status()
    data = resp.json()

    tasks = [dict(zip(data["job_property_names"], res)) for res in data["results"]]
    assert len(tasks) > 0

    # Task group is first task id
    task_group_id = tasks[0]["task_id"]

    # List task group from taskcluster as the code review task is not on treeherder
    queue = taskcluster.get_service("queue")
    group = queue.listTaskGroup(task_group_id)

    # And find the code-review-issues task in that group !
    return next(
        iter(
            [
                task
                for task in group["tasks"]
                if task["task"]["metadata"]["name"] == "code-review-issues"
            ]
        ),
        None,
    )


def go(min_date, max_date):
    # Start by authenticating on taskcluster
    taskcluster.auth()

    # And load secret
    taskcluster.load_secrets(
        "project/relman/code-review/runtime-production",
        prefixes=["common"],
        required=["PHABRICATOR"],
    )

    # Load hook service
    hooks = taskcluster.get_service("hooks")

    # Retrieve known updates from code review backend
    print(f"Loading known revisions from {min_date} to {max_date}")
    revisions, updates = list_diffs(min_date, max_date)
    print(f"Got {len(revisions)} mercurial revisions")
    print(f"Got {len(updates)} phab revision updates")

    # Process all pushes without a review task in backend
    # and when their revision has no update
    for push in list_pushes(revisions, updates, min_date, max_date):
        print(f"Triggering push {push['id']} @ {push['revision']}")
        task = find_task(push["id"])
        if not task:
            print("No code review task found !")
            continue

        payload = {
            "TRY_RUN_ID": task["status"]["runs"][0]["runId"],
            "TRY_TASK_GROUP_ID": task["status"]["taskGroupId"],
            "TRY_TASK_ID": task["status"]["taskId"],
        }
        print(f"Found code review task as {payload['TRY_TASK_ID']}")

        new_task = hooks.triggerHook(
            "project-relman", "code-review-production", payload
        )
        print(f" > Running in {new_task['status']['taskId']}")


if __name__ == "__main__":
    now = datetime.utcnow()
    go(now - timedelta(days=2), now - timedelta(seconds=2 * 3600))
