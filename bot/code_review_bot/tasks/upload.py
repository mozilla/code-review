# -*- coding: utf-8 -*-
import rs_parsepatch
import structlog

from code_review_bot import Issue
from code_review_bot import taskcluster
from code_review_bot.tasks.base import AnalysisTask
from libmozdata.phabricator import PhabricatorAPI

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

COMMENT_LINK_TO_DOC = """
Generated Doc can be accessed [here]({link_to_doc}).
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

    artifacts = ["public/firefox-source-docs-url.txt"]

    @property
    def display_name(self):
        return "doc-upload"

    def parse_issues(self, artifacts, revision):
        artifact = artifacts.get("public/firefox-source-docs-url.txt")
        if artifact is None:
            logger.warn("Missing firefox-source-docs-url.txt")
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

    def upload_link(self, artifacts, revision):
        phabricator = taskcluster.secrets["PHABRICATOR"]
        phabricator_api = PhabricatorAPI(phabricator["api_key"], phabricator["url"])
        assert isinstance(phabricator_api, PhabricatorAPI)
        artifact = artifacts.get("public/firefox-source-docs-url.txt")
        link_to_doc = artifact.get("Doc")
        comment = COMMENT_LINK_TO_DOC.format(link_to_doc=link_to_doc)
        self.phabricator_api.comment(
            revision.id,
            comment,
        )
