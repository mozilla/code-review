# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


from code_review_bot.tools.taskcluster import (
    load_task_group,
)


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
