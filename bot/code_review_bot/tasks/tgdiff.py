# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os
from urllib.parse import unquote

import structlog

from code_review_bot.tasks.base import NoticeTask

logger = structlog.get_logger(__name__)

COMMENT_TASKGRAPH_DIFF = """
NOTE: Tasks were added or removed in diff {diff_id}.

The following parameter set{s} {have} differences:

  * {markdown_links}
"""


class TaskGraphDiffTask(NoticeTask):
    """
    Notify when CI task configuration has changed.
    """

    artifact_urls = {}  # map of artifact name to url

    @property
    def display_name(self):
        return "taskgraph-diff"

    def load_artifacts(self, queue_service):
        # Process only the supported final states
        # as some tasks do not always have relevant output
        if self.state in self.skipped_states:
            logger.info("Skipping task", state=self.state, id=self.id, name=self.name)
            return
        elif self.state not in self.valid_states:
            logger.warning(
                "Invalid task state", state=self.state, id=self.id, name=self.name
            )
            return

        logger.info("List artifacts", task_id=self.id)
        try:
            self.artifact_urls = {
                a["name"]: queue_service.buildUrl(
                    "getArtifact", self.id, self.run_id, a["name"]
                )
                for a in queue_service.listArtifacts(self.id, self.run_id)["artifacts"]
                if a["name"].startswith("public/taskgraph/diffs/")
            }
        except Exception as e:
            logger.warn(
                "Failed to list artifacts",
                task_id=self.id,
                run_id=self.run_id,
                error=e,
            )
            return

        # We don't actually want the contents of these artifacts, just their
        # urls (which are now stored in `self.artifact_urls`).
        return {}

    def build_notice(self, _, revision):
        if not self.artifact_urls:
            return ""

        urls = [unquote(url) for url in self.artifact_urls.values()]
        mdlinks = []
        for url in urls:
            name = url.rsplit("/", 1)[-1]
            name = os.path.splitext(name)[0]
            if name.startswith("diff_"):
                name = name[len("diff_") :]
            mdlinks.append(f"[{name}]({url})")

        mdlinks = "\n  * ".join(mdlinks)
        return COMMENT_TASKGRAPH_DIFF.format(
            diff_id=revision.diff_id,
            s="s" if len(urls) > 1 else "",
            have="have" if len(urls) > 1 else "has",
            markdown_links=mdlinks,
        )
