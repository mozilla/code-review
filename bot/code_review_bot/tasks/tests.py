# -*- coding: utf-8 -*-
import re

import structlog

from code_review_bot import Issue
from code_review_bot import Level
from code_review_bot.tasks.base import AnalysisTask

logger = structlog.get_logger(__name__)

FAILURE_REGEX = re.compile(
    r"^\[([\w:\.\- ]+)\] TEST-UNEXPECTED-FAIL (.*)$", re.MULTILINE
)

ISSUE_MARKDOWN = """
## test failure {analyzer}

- **Level**: {level}
- **Publishable**: {publishable}

```
{message}
```
"""


class TestsIssue(Issue):
    def __init__(self, analyzer, revision, message):
        self.analyzer = analyzer
        self.revision = revision
        self.message = message
        self.level = Level.Error
        self.path = ""

    def validates(self):
        """
        Tests issues are valid as long as they match the format
        """
        return True

    def as_text(self):
        """
        Build the text content for reporters
        """
        return "test {}: {}".format(self.level.name, self.message)

    def as_markdown(self):
        """
        Build the Markdown content for debug email
        """
        return ISSUE_MARKDOWN.format(
            analyzer=self.analyzer,
            level=self.level.value,
            message=self.message,
            publishable=self.is_publishable() and "yes" or "no",
        )


class TestsTask(AnalysisTask):
    """
    Parse TEST-UNEXCPECTED-FAIL failures from logs
    """

    artifacts = ["public/logs/live.log"]

    def parse_issues(self, artifacts, revision):
        """
        Parse issues from the task's live log
        """
        assert isinstance(artifacts, dict)

        return [
            TestsIssue(analyzer=self.name, revision=revision, message=match[1])
            for artifact in artifacts.values()
            for match in FAILURE_REGEX.findall(artifact.decode("utf-8"))
        ]
