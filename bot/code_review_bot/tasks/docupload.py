# -*- coding: utf-8 -*-
import os

import structlog

from code_review_bot.tasks.base import NoticeTask

logger = structlog.get_logger(__name__)

MAX_LINKS = 21

DOC_LINK = """
- file [{path}]({doc_url})
"""
COMMENT_LINKS_TO_DOC = """
NOTE: {nb_docs_hint} modified in diff {diff_id}

{pronoun} can be previewed for one week:{doc_urls}
"""

COMMENT_LINK_TO_DOC = """
NOTE: Several documentation files were modified in diff {diff_id}

They can be previewed [here]({doc_url}) for one week.
"""


def direct_doc_url(path, docs_url, trees):
    base_docs_url = os.path.dirname(docs_url)

    filename, _ = os.path.splitext(os.path.basename(path))
    dirname = os.path.dirname(path)

    for docs_match_in_trees, dirname_in_trees in trees.items():
        if dirname.startswith(dirname_in_trees):
            truncated_dirname = dirname.replace(dirname_in_trees, "", 1)
            # Forging the link towards the documentation
            return "/".join(
                part.strip("/")
                for part in [
                    base_docs_url,
                    docs_match_in_trees,
                    truncated_dirname,
                    f"{filename}.html",
                ]
                if part
            )

    # We didn't find a mapping for the file in the trees artifact, this should never happen
    logger.warn(
        "Found no match in the trees.json mapping to build a direct documentation link",
        file=path,
    )
    return docs_url


class DocUploadTask(NoticeTask):
    """
    Support doc-upload tasks
    """

    artifacts = ["public/firefox-source-docs-url.txt", "public/trees.json"]

    @property
    def display_name(self):
        return "doc-upload"

    def build_notice(self, artifacts, revision):
        artifact = artifacts.get("public/firefox-source-docs-url.txt")
        if artifact is None:
            logger.warn("Missing firefox-source-docs-url.txt")
            return ""

        doc_url = artifact.decode("utf-8")

        trees = artifacts.get("public/trees.json")
        if trees is None:
            logger.warn("Missing trees.json")

        doc_files = [
            file
            for file in revision.files
            if "docs" in file and file.endswith((".rst", ".md"))
        ]
        nb_docs = len(doc_files)
        if not nb_docs:
            logger.info(
                "Found no documentation file in revision, skipping comment creation"
            )
            return ""

        if not trees or nb_docs > MAX_LINKS:
            return COMMENT_LINK_TO_DOC.format(diff_id=revision.diff_id, doc_url=doc_url)

        nb_docs_hint = (
            f"{nb_docs} documentation files were"
            if nb_docs > 1
            else "A documentation file was"
        )
        pronoun = "They" if nb_docs > 1 else "It"
        doc_urls = "".join(
            [
                DOC_LINK.format(path=file, doc_url=direct_doc_url(file, doc_url, trees))
                for file in doc_files
            ]
        )
        return COMMENT_LINKS_TO_DOC.format(
            nb_docs_hint=nb_docs_hint,
            diff_id=revision.diff_id,
            pronoun=pronoun,
            doc_urls=doc_urls,
        )
