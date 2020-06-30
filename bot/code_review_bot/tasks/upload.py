# -*- coding: utf-8 -*-
import rs_parsepatch
import structlog

from code_review_bot import Issue
from code_review_bot import Level
from code_review_bot.config import settings
from code_review_bot import taskcluster
from code_review_bot.tasks.base import AnalysisTask
from code_review_bot.report.base import Reporter
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

    def upload_link(self, artifacts, revision):
        phabricator = taskcluster.secrets["PHABRICATOR"]
        phabricator_api = PhabricatorAPI(phabricator["api_key"], phabricator["url"])
        assert isinstance(phabricator_api, PhabricatorAPI)
        artifact = artifacts.get("public/link-to-uploaded-doc.json")
        link_to_doc = artifact.get("Doc")
        comment = COMMENT_LINK_TO_DOC.format(link_to_doc=link_to_doc)
        self.phabricator_api.comment(
            revision.id,
            comment,
        )


class DocUploadReporter(Reporter):

    def __init__(self, configuration={}, *args, **kwargs):
        if kwargs.get("api") is not None:
            self.setup_api(kwargs["api"])

        self.analyzers_skipped = configuration.get("analyzers_skipped", [])
        assert isinstance(
            self.analyzers_skipped, list
        ), "analyzers_skipped must be a list"

        self.frontend_diff_url = configuration.get(
            "frontend_diff_url", "https://code-review.moz.tools/#/diff/{diff_id}"
        )

    def setup_api(self, api):
        assert isinstance(api, PhabricatorAPI)
        self.api = api
        logger.info("Phabricator reporter enabled")

    def publish_s3_link(self, revision):
        """
        Summarize publishable issues through Phabricator comment
        """
        # link_to_doc get from artifact
        comment = COMMENT_LINK_TO_DOC.format(link_to_doc=link_to_doc)
        self.api.comment(
            revision.id,
            comment,
        )
        logger.info("Published S3 doc link")
