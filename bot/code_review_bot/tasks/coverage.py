# -*- coding: utf-8 -*-
import os

import structlog

from code_review_bot import Issue
from code_review_bot import Level
from code_review_bot.config import settings
from code_review_bot.tasks.base import AnalysisTask

logger = structlog.get_logger(__name__)

ISSUE_MARKDOWN = """
## coverage problem

- **Path**: {path}
- **Publishable**: {publishable}

```
{message}
```
"""


class CoverageIssue(Issue):
    def __init__(self, path, lineno, message, revision):
        super().__init__(
            "coverage",
            revision,
            path,
            line=lineno and int(lineno) or None,
            nb_lines=1,
            check="no-coverage",
            level=Level.Warning,
            message=message,
        )

    def is_publishable(self):
        """
        Coverage issues are always publishable, unless they are in header files
        """
        return self.validates()

    def validates(self):
        """
        Coverage issues are always publishable, unless they are in header files
        """
        _, ext = os.path.splitext(self.path)
        return ext.lower() in settings.cpp_extensions.union(settings.js_extensions)

    def as_text(self):
        """
        Build the text content for reporters
        """
        return self.message

    def as_markdown(self):
        """
        Build the Markdown content for the debug email
        """
        return ISSUE_MARKDOWN.format(
            path=self.path,
            message=self.message,
            publishable=self.is_publishable() and "yes" or "no",
        )


class ZeroCoverageTask(AnalysisTask):
    """
    List all issues found by coverage analysis on specified files
    Uses the most recent data from the code coverage bot
    """

    route = "project.relman.code-coverage.production.cron.latest"
    artifacts = ["public/zero_coverage_report.json"]

    def parse_issues(self, artifacts, revision):
        zero_coverage_files = {
            file_info["name"]
            for artifact in artifacts.values()
            for file_info in artifact["files"]
            if file_info["uncovered"]
        }

        return [
            CoverageIssue(path, 0, "This file is uncovered", revision)
            for path in revision.files
            if path in zero_coverage_files
        ]
