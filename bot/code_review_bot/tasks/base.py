# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from abc import ABC, abstractmethod

import structlog
import yaml

logger = structlog.get_logger(__name__)


class BaseTask:
    artifacts = []
    route = None
    valid_states = ("completed", "failed")
    skipped_states = ()
    extra_reviewers_groups = []

    def __init__(self, task_id, task_status):
        self.id = task_id
        assert "task" in task_status, f"No task data for {self.id}"
        assert "status" in task_status, f"No status data for {self.id}"
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

    @classmethod
    def build_from_route(cls, index_service, queue_service):
        """
        Build the task instance from a configured Taskcluster route
        """
        assert cls.route is not None, f"Missing route on {cls}"

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

    def load_artifact(self, queue_service, artifact_name):
        url = queue_service.buildUrl("getArtifact", self.id, self.run_id, artifact_name)
        # Allows HTTP_30x redirections retrieving the artifact
        response = queue_service.session.get(url, stream=True, allow_redirects=True)

        try:
            response.raise_for_status()
        except Exception as e:
            logger.warn(
                "Failed to read artifact",
                task_id=self.id,
                run_id=self.run_id,
                artifact=artifact_name,
                error=e,
            )
            return None, True

        # Load artifact's data, either as JSON or YAML
        if artifact_name.endswith(".json"):
            content = response.json()
        elif artifact_name.endswith(".yml") or artifact_name.endswith(".yaml"):
            content = yaml.load_stream(response.text)
        else:
            # Json responses are automatically parsed into Python structures
            content = response.content or None
        return content, False

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
            content, skip = self.load_artifact(queue_service, artifact_name)
            if skip:
                continue

            out[artifact_name] = content

        return out


class AnalysisTask(BaseTask, ABC):
    """
    An analysis CI task running on Taskcluster
    """

    def build_help_message(self, files):
        """
        An optional help message aimed at developers to reproduce the issues detection
        A list of relative paths with issues is specified to build a precise message
        By default it's empty (None)
        """

    def build_patches(self, artifacts):
        """
        Some analyzers can provide a patch applicable by developers
        These patches are stored as Taskcluster artifacts and reported to developers
        Output is a list of tuple (patch name as str, patch content as str)
        """
        return []

    @abstractmethod
    def parse_issues(self, artifacts, revision):
        """
        Given list of artifacts, return a list of Issue objects.
        """


class NoticeTask(BaseTask, ABC):
    """
    A task that simply displays information.
    """

    @abstractmethod
    def build_notice(self, artifacts, revision):
        """
        Return multiline string containing information to display.
        """
