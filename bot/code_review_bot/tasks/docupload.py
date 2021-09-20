# -*- coding: utf-8 -*-
import structlog

from code_review_bot.tasks.base import NoticeTask

logger = structlog.get_logger(__name__)


class DocUploadTask(NoticeTask):
    """
    Support doc-upload tasks
    """

    artifacts = ["public/firefox-source-docs-url.txt"]

    @property
    def display_name(self):
        return "doc-upload"

    def build_link(self, artifacts):
        artifact = artifacts.get("public/firefox-source-docs-url.txt")
        if artifact is None:
            logger.warn("Missing firefox-source-docs-url.txt")
            return ""

        return artifact.decode("utf-8")
