# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os.path
import time

import structlog

from code_review_bot.report.base import Reporter

logger = structlog.get_logger(__name__)


class DebugReporter(Reporter):
    """
    Debug the issues found and report through the logs
    Build a json file with all issues details, stored as a TC artifact
    """

    def __init__(self, output_dir):
        assert os.path.isdir(output_dir), "Invalid output dir"
        self.report_path = os.path.join(output_dir, "report.json")

    def publish(self, issues, revision, task_failures):
        """
        Display issues choices
        """
        # Simply output issues details through logging
        logger.info("Debug revision", rev=str(revision))
        for issue in issues:
            logger.info(
                "Issue {}".format(
                    "publishable" if issue.is_publishable() else "silent"
                ),
                issue=str(issue),
            )
        for task in task_failures:
            logger.info("Task failure detected", name=task.name, task=task.id)
        for patch in revision.improvement_patches:
            logger.info("Patch {}".format(patch))

        # Output json report in public directory
        report = {
            "time": time.time(),
            "revision": revision.as_dict(),
            "issues": [issue.as_dict() for issue in issues],
            "patches": {
                patch.analyzer.name: patch.url or patch.path
                for patch in revision.improvement_patches
            },
            "task_failures": [
                {"name": task.name, "id": task.id} for task in task_failures
            ],
        }
        with open(self.report_path, "w") as f:
            json.dump(report, f)
