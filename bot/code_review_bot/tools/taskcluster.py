# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import structlog

logger = structlog.get_logger(__name__)


def load_task_group(queue, group_id):
    tasks = {}

    def _load_tasks(page):
        assert "tasks" in page
        tasks.update({task["status"]["taskId"]: task for task in page["tasks"]})

    queue.listTaskGroup(group_id, paginationHandler=_load_tasks)
    return tasks
