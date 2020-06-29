# -*- coding: utf-8 -*-
import rs_parsepatch
import structlog

from code_review_bot import Issue
from code_review_bot import Level
from code_review_bot.config import settings
from code_review_bot.tasks.base import AnalysisTask

logger = structlog.get_logger(__name__)

ISSUE_MARKDOWN = """
## issue {analyzer}

- **Path**: {path}
- **Level**: {level}
- **Check**: {check}
- **Line**: {line}
- **Publishable**: {publishable}

```
{message}
```
"""


class DocUploadIssue(Issue):
    def validates(self):
        """
        Default issues are valid as long as they match the format
        """
        return True

    def as_text(self):
        """
        Build the text content for reporters
        """
        return "{}: {} [{}]".format(self.level.name, self.message, self.check)

    def as_markdown(self):
        """
        Build the Markdown content for debug email
        """
        return ISSUE_MARKDOWN.format(
            analyzer=self.analyzer.name,
            path=self.path,
            check=self.check,
            level=self.level.value,
            line=self.line,
            message=self.message,
            publishable=self.is_publishable() and "yes" or "no",
        )


class DocUploadTask(AnalysisTask):
    """
    Support issues from source-test clang-format tasks by reading the
    clang-format json output
    """

    artifacts = ["public/link-to-uploaded-doc.json"]

    @property
    def display_name(self):
        return "doc-upload"

    def parse_issues(self, artifacts, revision):
        artifact = artifacts.get("public/link-to-uploaded-doc.json")
        if artifact is None:
            logger.warn("Missing link-to-uploaded-doc.json")
            return []

        # Use all chunks provided by parsepatch
        return [
            DocUploadIssue(
                analyzer=self,
                path=diff["filename"],
                lines=diff["lines"],
                revision=revision,
            )
            for diff in rs_parsepatch.get_diffs(artifact)
        ]
