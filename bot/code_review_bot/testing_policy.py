# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""
Automatically set the Firefox testing policy tag on Phabricator revisions.

See https://firefox-source-docs.mozilla.org/testing/testing-policy/index.html
"""

import fnmatch
import os
import re

import structlog

logger = structlog.get_logger(__name__)

# Phabricator project tagging commits that do not change behavior for end users
# (documentation, test-only changes, ...)
TESTING_EXCEPTION_UNCHANGED_PHID = "PHID-PROJ-cspmf33ku3kjaqtuvs7g"

# Phabricator project tagging commits that only change UI styling, images or localized strings
TESTING_EXCEPTION_UI_PHID = "PHID-PROJ-zjipshabawolpkllehvg"

# Phabricator project tagging commits that come with their own tests
TESTING_APPROVED_PHID = "PHID-PROJ-h7y4cs7m2o67iczw62pp"

# All the testing policy projects on Phabricator, a revision should only have one of them
TESTING_POLICY_TAG_PHIDS = frozenset(
    [
        TESTING_APPROVED_PHID,  # testing-approved
        TESTING_EXCEPTION_UNCHANGED_PHID,  # testing-exception-unchanged
        TESTING_EXCEPTION_UI_PHID,  # testing-exception-ui
        "PHID-PROJ-e4fcjngxcws3egiecv3r",  # testing-exception-elsewhere
        "PHID-PROJ-iciyosoekrczpf2a4emw",  # testing-exception-other
    ]
)

# Files with these extensions are documentation
DOC_EXTENSIONS = frozenset([".md", ".rst"])

# Files named like this (e.g. README, README.txt, LICENSE-MIT) are documentation
DOC_FILENAME_REGEX = re.compile(
    r"^(readme|license|licence|copying|changelog|authors|contributing)"
    r"(-[a-z0-9]+(\.[0-9]+)?)*(\.(txt|md|rst|html))?$"
)

# Files with these extensions only change UI styling, images or localized strings
UI_EXTENSIONS = frozenset(
    [
        # Styling
        ".css",
        # Images
        ".svg",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".icns",
        ".webp",
        ".avif",
        # Fonts
        ".ttf",
        ".otf",
        ".woff",
        ".woff2",
        # Localized strings
        ".ftl",
        ".properties",
        ".dtd",
    ]
)

# Test manifests and expectations, which do not add coverage by themselves
TEST_MANIFEST_EXTENSIONS = frozenset([".toml", ".list", ".ini"])

# Test files or manifests recognized by their basename
TEST_BASENAME_PATTERNS = (
    "test_*",
    "browser_*.js",
    "browser_*.mjs",
    "mochitest*.toml",
    "browser*.toml",
    "chrome*.toml",
    "xpcshell*.toml",
    "a11y*.toml",
    "python*.toml",
    "reftest*.list",
    "crashtests*.list",
    "jstests*.list",
)


def is_doc_path(path):
    """
    Check if a path only holds documentation
    """
    filename = path.rsplit("/", 1)[-1]
    _, ext = os.path.splitext(filename)

    if ext.lower() in DOC_EXTENSIONS:
        return True

    return DOC_FILENAME_REGEX.match(filename.lower()) is not None


# This code was adapted from https://github.com/mozsearch/mozsearch/blob/2e24a308bf66b4c149683bfeb4ceeea3b250009a/router/router.py#L127
# and should be kept in sync, except that only web-platform tests are considered under testing/, not the test harnesses.
def is_test(path):
    """
    Check if a path is under a test directory
    """
    return (
        "/test/" in path
        or "/tests/" in path
        or "/mochitest/" in path
        or "/unit/" in path
        or "/gtest/" in path
        or path.startswith("testing/web-platform/")
        or "/jsapi-tests/" in path
        or "/reftests/" in path
        or "/reftest/" in path
        or "/crashtests/" in path
        or "/crashtest/" in path
        or "/gtests/" in path
        or "/googletest/" in path
    )


def is_test_path(path):
    """
    Check if a path is a test file, a test manifest or test metadata
    """
    if is_test(path):
        return True

    filename = path.rsplit("/", 1)[-1]
    return any(
        fnmatch.fnmatch(filename.lower(), pattern) for pattern in TEST_BASENAME_PATTERNS
    )


def is_test_file(path):
    """
    Check if a path is an actual test, not a manifest or expectation file
    """
    _, ext = os.path.splitext(path)
    return is_test_path(path) and ext.lower() not in TEST_MANIFEST_EXTENSIONS


def is_unchanged_path(path):
    """
    Check if a path modification cannot change behavior for end users
    """
    return is_doc_path(path) or is_test_path(path)


def is_ui_path(path):
    """
    Check if a path only holds UI styling, images or localized strings
    """
    _, ext = os.path.splitext(path)
    return ext.lower() in UI_EXTENSIONS


def detect_testing_policy_tag(files):
    """
    Detect the testing policy tag that applies to a patch, from its list of modified files.
    Returns a Phabricator project PHID, or None when the heuristics are not conclusive.
    """
    files = list(files)
    if not files:
        return None

    # Only documentation or tests: nothing changes for end users
    if all(is_unchanged_path(path) for path in files):
        return TESTING_EXCEPTION_UNCHANGED_PHID

    # Only UI styling, images or strings (possibly along with documentation or tests)
    if all(is_unchanged_path(path) or is_ui_path(path) for path in files):
        return TESTING_EXCEPTION_UI_PHID

    # Code changes coming along with test changes are covered
    if any(is_test_file(path) for path in files):
        return TESTING_APPROVED_PHID

    return None


def has_testing_policy_tag(project_phids):
    """
    Check if any of the provided Phabricator projects is a testing policy tag
    """
    return not TESTING_POLICY_TAG_PHIDS.isdisjoint(project_phids)


def was_tag_removed(api, revision, tag_phid):
    """
    Check the revision's history to know if the tag has been explicitly removed
    (probably by a human disagreeing with the bot), so we do not add it again
    """
    transactions = api.request(
        "transaction.search", objectIdentifier=revision.phabricator_phid
    )
    for transaction in transactions.get("data") or []:
        if transaction.get("type") != "projects":
            continue
        for operation in transaction.get("fields", {}).get("operations", []):
            if (
                operation.get("operation") == "remove"
                and operation.get("phid") == tag_phid
            ):
                return True
    return False


def apply_testing_policy_tag(api, revision):
    """
    Set the testing policy tag on a revision when it can be safely
    deduced from the modified files, and no tag has been set yet.
    Returns the PHID of the tag added, or None when nothing was done.
    """
    tag_phid = detect_testing_policy_tag(revision.files)
    if tag_phid is None:
        return None

    try:
        # Load the projects currently set on the revision
        revision_data = api.load_revision(
            rev_id=revision.phabricator_id, attachments={"projects": True}
        )
        project_phids = (
            revision_data.get("attachments", {})
            .get("projects", {})
            .get("projectPHIDs", [])
        )

        # Never override a testing policy tag set by a human
        if has_testing_policy_tag(project_phids):
            logger.info(
                "Revision already has a testing policy tag, taking no action",
                revision=revision,
            )
            return None

        # Do not re-add a tag someone explicitly removed
        if was_tag_removed(api, revision, tag_phid):
            logger.info(
                "Testing policy tag was previously removed, taking no action",
                revision=revision,
                tag=tag_phid,
            )
            return None

        api.edit_revision(
            revision.phabricator_id,
            [{"type": "projects.add", "value": [tag_phid]}],
        )
    except Exception as e:
        # Tagging is a best effort feature that should never block the publication
        logger.warning(
            "Failed to set the testing policy tag", revision=revision, error=str(e)
        )
        return None

    logger.info("Set testing policy tag on revision", revision=revision, tag=tag_phid)
    return tag_phid
