# -*- coding: utf-8 -*-
import structlog

from code_review_bot.tasks.base import AnalysisTask

logger = structlog.get_logger(__name__)


class DocUploadTask(AnalysisTask):
    """
    Support doc-upload tasks
    """

    artifacts = ["public/firefox-source-docs-url.txt"]

    @property
    def display_name(self):
        return "doc-upload"

    def parse_issues(self, artifacts, revision):
        return []

    def build_link(self, artifacts):
        artifact = artifacts.get("public/firefox-source-docs-url.txt")
        if artifact is None:
            logger.warn("Missing firefox-source-docs-url.txt")
            return ""

        return artifact.decode("utf-8")
