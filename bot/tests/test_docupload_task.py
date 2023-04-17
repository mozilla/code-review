# -*- coding: utf-8 -*-
import pytest

from code_review_bot.tasks.docupload import MAX_LINKS, DocUploadTask

ARTIFACTS = {
    "public/firefox-source-docs-url.txt": b"http://firefox-test-docs.mozilla.org/index.html",
    "public/trees.json": {
        "section1": "docs/folderA",
        "section2": "docs/folderB/folderC",
    },
}

MISSING_MAPPING_OR_MORE_THAN_TWENTY = """
NOTE: Several documentation files were modified in diff 42

They can be previewed [here](http://firefox-test-docs.mozilla.org/index.html) for one week.
"""

ONE_DIRECT_LINK = """
NOTE: A documentation file was modified in diff 42

It can be previewed for one week:
- file [docs/folderA/index.rst](http://firefox-test-docs.mozilla.org/section1/index.html)

"""

VARIOUS_DIRECT_LINKS = """
NOTE: 3 documentation files were modified in diff 42

They can be previewed for one week:
- file [docs/folderA/index.rst](http://firefox-test-docs.mozilla.org/section1/index.html)

- file [docs/folderB/folderC/index.rst](http://firefox-test-docs.mozilla.org/section2/index.html)

- file [docs/folderB/folderC/subfolder/index.md](http://firefox-test-docs.mozilla.org/section2/subfolder/index.html)

"""


VARIOUS_DIRECT_LINKS_WITH_EXTRA_DOC_FILES = """
NOTE: 4 documentation files were modified in diff 42

They can be previewed for one week:
- file [docs/folderA/index.rst](http://firefox-test-docs.mozilla.org/section1/index.html)

- file [docs/folderB/folderC/index.rst](http://firefox-test-docs.mozilla.org/section2/index.html)

- file [docs/folderB/folderC/subfolder/index.md](http://firefox-test-docs.mozilla.org/section2/subfolder/index.html)

- file [mots.yaml](http://firefox-test-docs.mozilla.org/index.html)

"""


@pytest.fixture
def mock_doc_upload_task():
    doc_task_status = {
        "task": {"metadata": {"name": "source-test-doc-upload"}},
        "status": {
            "taskId": "12345deadbeef",
            "state": "completed",
            "runs": [{"runId": 0}],
        },
    }
    return DocUploadTask("12345deadbeef", doc_task_status)


def test_build_notice_no_docs_url_artifact(mock_revision, mock_doc_upload_task):
    artifacts = ARTIFACTS.copy()
    del artifacts["public/firefox-source-docs-url.txt"]

    mock_revision.files = ["file1.txt", "docs/folderA/index.rst"]
    notice = mock_doc_upload_task.build_notice(artifacts, mock_revision)
    assert notice == ""


def test_build_notice_no_trees_artifact(mock_revision, mock_doc_upload_task):
    artifacts = ARTIFACTS.copy()
    del artifacts["public/trees.json"]

    mock_revision.files = ["file1.txt", "docs/folderA/index.rst"]
    notice = mock_doc_upload_task.build_notice(artifacts, mock_revision)
    assert notice == ""


def test_build_notice_no_documentation_file(mock_revision, mock_doc_upload_task):
    mock_revision.files = ["file1.txt", "docs/folderA/index.svg"]
    notice = mock_doc_upload_task.build_notice(ARTIFACTS, mock_revision)
    assert notice == ""


def test_build_notice_more_than_twenty_files(mock_revision, mock_doc_upload_task):
    mock_revision.files = ["file1.txt"] + ["docs/folderA/index.rst"] * 30
    assert len(mock_revision.files) > MAX_LINKS
    notice = mock_doc_upload_task.build_notice(ARTIFACTS, mock_revision)
    assert notice == MISSING_MAPPING_OR_MORE_THAN_TWENTY


def test_build_notice_only_one_file(mock_revision, mock_doc_upload_task):
    mock_revision.files = ["file1.txt", "docs/folderA/index.rst"]
    notice = mock_doc_upload_task.build_notice(ARTIFACTS, mock_revision)
    assert notice == ONE_DIRECT_LINK


def test_build_notice_various_files(mock_revision, mock_doc_upload_task):
    mock_revision.files = [
        "file1.txt",  # not a documentation file (bad prefix and bad extension)
        "docs/folderA/image.svg",  # not a documentation file (bad extension)
        "docs/folderA/index.rst",  # complete match on "folderA"
        "docs/folderB/folderC/index.rst",  # complete match on "folderB/folderC"
        "docs/folderB/folderC/subfolder/index.md",  # partial match on a prefix "folderB/folderC"
        "docs/folderD/index.rst",  # not a documentation file (bad prefix)
    ]
    notice = mock_doc_upload_task.build_notice(ARTIFACTS, mock_revision)
    assert notice == VARIOUS_DIRECT_LINKS


def test_build_notice_various_files_with_extra_doc_files(
    mock_revision, mock_doc_upload_task
):
    mock_revision.files = [
        "file1.txt",  # not a documentation file (bad prefix and bad extension)
        "docs/folderA/image.svg",  # not a documentation file (bad extension)
        "docs/folderA/index.rst",  # complete match on "folderA"
        "docs/folderB/folderC/index.rst",  # complete match on "folderB/folderC"
        "docs/folderB/folderC/subfolder/index.md",  # partial match on a prefix "folderB/folderC"
        "docs/folderD/index.rst",  # not a documentation file (bad prefix)
        "mots.yaml",  # mots.yaml as an additional file to trigger docupload build notice
    ]
    notice = mock_doc_upload_task.build_notice(ARTIFACTS, mock_revision)
    assert notice == VARIOUS_DIRECT_LINKS_WITH_EXTRA_DOC_FILES
