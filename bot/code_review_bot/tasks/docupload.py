# -*- coding: utf-8 -*-
import structlog

from code_review_bot.tasks.base import NoticeTask

logger = structlog.get_logger(__name__)

COMMENT_LINK_TO_DOC = """
NOTE: Documentation was modified in diff {diff_id}

It can be previewed [here]({doc_url}) for one week.
"""


class DocUploadTask(NoticeTask):
    """
    Support doc-upload tasks
    """

    artifacts = ["public/firefox-source-docs-url.txt"]

    @property
    def display_name(self):
        return "doc-upload"

    def build_notice(self, artifacts, revision):
        artifact = artifacts.get("public/firefox-source-docs-url.txt")
        if artifact is None:
            logger.warn("Missing firefox-source-docs-url.txt")
            return ""

        doc_url = artifact.decode("utf-8")
        return COMMENT_LINK_TO_DOC.format(diff_id=revision.diff_id, doc_url=doc_url)
