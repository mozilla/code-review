# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import structlog

from code_review_bot import taskcluster as tc_config
from code_review_bot.tasks.base import NoticeTask

logger = structlog.get_logger(__name__)

REPORT_ARTIFACT = "public/screenshot-diffs/index.html"
REPORT_LINK = (
    "{root_url}/api/queue/v1/task/{task_id}/runs/{run_id}/artifacts/" + REPORT_ARTIFACT
)

COMMENT_SCREENSHOT_REPORT = """
Note: Screenshot tests report changes in diff {diff_id} ({name}).

The screenshot differences against the recorded baseline can be reviewed in the [test report]({url}).
"""


class ScreenshotTestTask(NoticeTask):
    """
    Link the HTML report produced by a failed screenshot test task
    """

    artifacts = [REPORT_ARTIFACT]

    # Only a failed run has a report worth showing
    valid_states = ("failed",)
    skipped_states = ("completed",)

    def build_notice(self, artifacts, revision):
        if REPORT_ARTIFACT not in artifacts:
            logger.info("No screenshot report found", task_id=self.id)
            return ""
        url = REPORT_LINK.format(
            root_url=tc_config.default_url, task_id=self.id, run_id=self.run_id
        )
        return COMMENT_SCREENSHOT_REPORT.format(
            diff_id=revision.diff_id, name=self.name, url=url
        )
