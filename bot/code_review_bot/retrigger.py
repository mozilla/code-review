# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import requests

from code_review_bot import taskcluster

TC_INDEX_URL = (
    "https://firefox-ci-tc.services.mozilla.com/api/index/v1/tasks/project.relman.{}.code-review.phabricator"
)


def list_tasks(env):
    url = TC_INDEX_URL.format(env)
    resp = requests.get(url)
    resp.raise_for_status()
    return list(map(lambda t: t["data"], resp.json()["tasks"]))


def is_mach_failure(issue):
    return issue["state"] == "error" and issue.get("error_code") == "mach"


def is_not_error(issue):
    return issue["state"] != "error"


def main(env):
    taskcluster.auth()
    hooks = taskcluster.get_service("hooks")

    # List all tasks on the env
    all_tasks = list_tasks(env)

    # List non erroneous tasks
    skip_phids = [t["diff_phid"] for t in filter(is_not_error, all_tasks)]

    # Get tasks with a mach failure
    tasks = list(filter(is_mach_failure, all_tasks))

    # Trigger all mach error tasks
    total = 0
    for task in tasks:
        phid = task["diff_phid"]
        print("Triggering {} > {}".format(phid, task["title"]))

        if phid in skip_phids:
            print(">> Skipping, phid {} has already a non-erroneous task".format(phid))
            continue

        extra_env = {"ANALYSIS_SOURCE": "phabricator", "ANALYSIS_ID": phid}
        task = hooks.triggerHook(
            "project-relman", "code-review-{}".format(env), extra_env
        )
        print(">> New task {}".format(task["status"]["taskId"]))
        total += 1

    print("Triggered {} tasks".format(total))


if __name__ == "__main__":
    main("production")
