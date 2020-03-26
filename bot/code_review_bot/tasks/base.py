# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import structlog

logger = structlog.get_logger(__name__)


class AnalysisTask(object):
    """
    An analysis CI task running on Taskcluster
    """

    artifacts = []
    route = None
    valid_states = ("completed", "failed")
    skipped_states = ()

    def __init__(self, task_id, task_status):
        self.id = task_id
        assert "task" in task_status, "No task data for {}".format(self.id)
        assert "status" in task_status, "No status data for {}".format(self.id)
        self.task = task_status["task"]
        self.status = task_status["status"]

    @property
    def run_id(self):
        return self.status["runs"][-1]["runId"]

    @property
    def name(self):
        """Short name used to identify the task"""
        return self.task["metadata"].get("name", "unknown")

    @property
    def display_name(self):
        """
        Longer name used to describe the task to humans
        By default fallback to short name
        """
        return self.name

    @property
    def state(self):
        return self.status["state"]

    def build_help_message(self, files):
        """
        An optional help message aimed at developers to reproduce the issues detection
        A list of relative paths with issues is specified to build a precise message
        By default it's empty (None)
        """

    @classmethod
    def build_from_route(cls, index_service, queue_service):
        """
        Build the task instance from a configured Taskcluster route
        """
        assert cls.route is not None, "Missing route on {}".format(cls)

        # Load its task id
        try:
            index = index_service.findTask(cls.route)
            task_id = index["taskId"]
            logger.info("Loaded task from route", cls=cls, task_id=task_id)
        except Exception as e:
            logger.warn("Failed loading task from route", route=cls.route, error=str(e))
            return

        # Load the task & status description
        try:
            task_status = queue_service.status(task_id)
            task_status["task"] = queue_service.task(task_id)
        except Exception as e:
            logger.warn("Task not found", task=task_id, error=str(e))
            return

        # Build the instance
        return cls(task_id, task_status)

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

        # Load relevant artifacts
        out = {}
        for artifact_name in self.artifacts:
            logger.info("Load artifact", task_id=self.id, artifact=artifact_name)
            try:
                artifact = queue_service.getArtifact(
                    self.id, self.run_id, artifact_name
                )

                if "response" in artifact:
                    # When the response's content is empty, set content to None
                    content = artifact["response"].content or None
                else:
                    # Json responses are automatically parsed into Python structures
                    content = artifact
                out[artifact_name] = content
            except Exception as e:
                logger.warn(
                    "Failed to read artifact",
                    task_id=self.id,
                    run_id=self.run_id,
                    artifact=artifact_name,
                    error=e,
                )
                continue

        return out

    def build_patches(self, artifacts):
        """
        Some analyzers can provide a patch applicable by developers
        These patches are stored as Taskcluster artifacts and reported to developers
        Output is a list of tuple (patch name as str, patch content as str)
        """
        return []
