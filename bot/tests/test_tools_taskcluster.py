# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest

from code_review_bot.tools.taskcluster import (
    find_ancestors,
    find_blocked,
    is_code_review_task,
    load_statuses,
    load_task_group,
)


def _task(state, dependencies=(), routes=(), reason=None):
    task = {"dependencies": list(dependencies), "routes": list(routes)}
    run = {"runId": 0}
    if reason is not None:
        run["reasonResolved"] = reason
    return {"task": task, "status": {"state": state, "runs": [run]}}


def _statuses(tasks):
    return {task_id: task["status"] for task_id, task in tasks.items()}


@pytest.mark.parametrize(
    "routes, expected",
    [
        (["project.relman.codereview.v1.try_ending"], True),
        (["project.relman.codereview-build-test.v1.try_ending"], True),
        (
            ["index.project.relman.codereview.v1.task_groups.abcdef"],
            False,
        ),
        ([], False),
    ],
)
def test_is_code_review_task(routes, expected):
    assert is_code_review_task({"routes": routes}) is expected


def test_find_blocked_chain():
    tasks = {
        "code-review": _task("unscheduled", ["test", "other-build", "running"]),
        "toolchain": _task("failed"),
        "fetch": _task("completed"),
        "build": _task("unscheduled", ["toolchain", "fetch"]),
        "test": _task("unscheduled", ["build"]),
        "other-build": _task("unscheduled", ["fetch"]),
        "running": _task("running", ["toolchain"]),
    }

    assert find_blocked(tasks, _statuses(tasks), ["code-review"]) == {
        "build",
        "test",
    }


@pytest.mark.parametrize("reason", ["canceled", "deadline-exceeded", "worker-shutdown"])
def test_find_blocked_exception(reason):
    tasks = {
        "code-review": _task("unscheduled", ["build"]),
        "docker-image": _task("exception", reason=reason),
        "build": _task("unscheduled", ["docker-image"]),
    }

    assert find_blocked(tasks, _statuses(tasks), ["code-review"]) == {"build"}


def test_find_blocked_only_dependencies_of_start_tasks():
    tasks = {
        "code-review": _task("unscheduled", ["build"]),
        "other-code-review": _task("unscheduled", ["other-build"]),
        "toolchain": _task("failed"),
        "build": _task("unscheduled", ["toolchain"]),
        "other-build": _task("unscheduled", ["toolchain"]),
        "unrelated": _task("unscheduled", ["toolchain"]),
    }

    assert find_blocked(tasks, _statuses(tasks), ["code-review"]) == {"build"}
    assert find_blocked(
        tasks, _statuses(tasks), ["code-review", "other-code-review"]
    ) == {"build", "other-build"}


def test_find_blocked_all_dependencies_of_blocked_task():
    tasks = {
        "code-review": _task("unscheduled", ["test"]),
        "toolchain": _task("failed"),
        "fetch": _task("failed"),
        "build": _task("unscheduled", ["fetch"]),
        "test": _task("unscheduled", ["toolchain", "build"]),
    }

    assert find_blocked(tasks, _statuses(tasks), ["code-review"]) == {
        "build",
        "test",
    }


class LookupRecorder(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lookups = []

    def get(self, key, default=None):
        self.lookups.append(key)
        return super().get(key, default)


def test_find_blocked_visits_tasks_once():
    tasks = LookupRecorder(
        {
            "code-review": _task("unscheduled", ["test", "other-test", "build"]),
            "toolchain": _task("failed"),
            "build": _task("unscheduled", ["toolchain"]),
            "test": _task("unscheduled", ["build"]),
            "other-test": _task("unscheduled", ["build"]),
        }
    )

    assert find_blocked(tasks, _statuses(tasks), ["code-review"]) == {
        "build",
        "test",
        "other-test",
    }
    assert sorted(tasks.lookups) == ["build", "other-test", "test", "toolchain"]


def test_find_blocked_external_dependency():
    tasks = {
        "code-review": _task("unscheduled", ["build", "other-build"]),
        "build": _task("unscheduled", ["external-toolchain"]),
        "other-build": _task("unscheduled", ["unknown-toolchain"]),
    }
    statuses = {
        **_statuses(tasks),
        "external-toolchain": _task("failed")["status"],
    }

    assert find_blocked(tasks, statuses, ["code-review"]) == {"build"}


def test_find_ancestors():
    tasks = {
        "code-review": _task("completed", ["test", "external"]),
        "other-code-review": _task("completed", ["lint"]),
        "toolchain": _task("failed"),
        "build": _task("exception", ["toolchain", "fetch"], reason="canceled"),
        "fetch": _task("completed"),
        "test": _task("exception", ["build"], reason="canceled"),
        "lint": _task("exception", ["docker-image"], reason="canceled"),
        "docker-image": _task("failed"),
    }

    assert find_ancestors(tasks, ["code-review"]) == {
        "test",
        "build",
        "toolchain",
        "fetch",
    }
    assert find_ancestors(tasks, ["code-review", "other-code-review"]) == {
        "test",
        "build",
        "toolchain",
        "fetch",
        "lint",
        "docker-image",
    }


class FakeQueue:
    def __init__(self, statuses):
        self.statuses = statuses
        self.status_calls = []

    def status(self, task_id):
        self.status_calls.append(task_id)
        return {"status": self.statuses[task_id]}

    def listTaskGroup(self, group_id, paginationHandler):
        for task_id in ("a", "b"):
            paginationHandler({"tasks": [{"task": {}, "status": {"taskId": task_id}}]})


def test_load_task_group():
    assert load_task_group(FakeQueue({}), "group") == {
        "a": {"task": {}, "status": {"taskId": "a"}},
        "b": {"task": {}, "status": {"taskId": "b"}},
    }


def test_load_statuses():
    queue = FakeQueue({"toolchain": _task("failed")["status"]})

    assert load_statuses(queue, ["toolchain", "missing"]) == {
        "toolchain": _task("failed")["status"]
    }
    assert queue.status_calls == ["toolchain", "missing"]
