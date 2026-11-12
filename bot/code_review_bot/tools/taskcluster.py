# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import structlog

logger = structlog.get_logger(__name__)

CODE_REVIEW_ROUTE_PREFIX = "project.relman.codereview"
CODE_REVIEW_ROUTE_SUFFIX = ".v1.try_ending"


def is_code_review_task(task):
    return any(
        route.startswith(CODE_REVIEW_ROUTE_PREFIX)
        and route.endswith(CODE_REVIEW_ROUTE_SUFFIX)
        for route in task.get("routes", [])
    )


def find_ancestors(tasks, start_ids):
    ancestors = set()
    pending = [
        dep_id
        for task_id in start_ids
        for dep_id in tasks[task_id]["task"].get("dependencies", [])
    ]
    while pending:
        task_id = pending.pop()
        if task_id in ancestors or task_id not in tasks:
            continue
        ancestors.add(task_id)
        pending.extend(tasks[task_id]["task"].get("dependencies", []))
    return ancestors


def find_blocked(tasks, statuses, start_ids):
    blocked = {}

    def _visit(task_id):
        if task_id in blocked:
            return blocked[task_id]
        blocked[task_id] = False
        task = tasks.get(task_id)
        if task is None or task["status"]["state"] != "unscheduled":
            return False
        dependencies = task["task"].get("dependencies", [])
        blocked_dependencies = [_visit(dep_id) for dep_id in dependencies]
        blocked[task_id] = any(blocked_dependencies) or any(
            dep_id in statuses and statuses[dep_id]["state"] in ("failed", "exception")
            for dep_id in dependencies
        )
        return blocked[task_id]

    for task_id in start_ids:
        for dep_id in tasks[task_id]["task"].get("dependencies", []):
            _visit(dep_id)

    return {task_id for task_id, is_blocked in blocked.items() if is_blocked}


def load_task_group(queue, group_id):
    tasks = {}

    def _load_tasks(page):
        assert "tasks" in page
        tasks.update({task["status"]["taskId"]: task for task in page["tasks"]})

    queue.listTaskGroup(group_id, paginationHandler=_load_tasks)
    return tasks


def load_statuses(queue, task_ids):
    statuses = {}
    for task_id in task_ids:
        try:
            statuses[task_id] = queue.status(task_id)["status"]
        except Exception as e:
            logger.warn("Failed to load a task status", task=task_id, error=str(e))
    return statuses
