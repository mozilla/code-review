# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from unittest.mock import MagicMock

import pytest

from code_review_bot.testing_policy import (
    TESTING_APPROVED_PHID,
    TESTING_EXCEPTION_UI_PHID,
    TESTING_EXCEPTION_UNCHANGED_PHID,
    apply_testing_policy_tag,
    detect_testing_policy_tag,
    is_test_file,
    is_ui_path,
    is_unchanged_path,
)

REVISION_ID = 51
REVISION_PHID = "PHID-DREV-test"
OTHER_PROJECT_PHID = "PHID-PROJ-other"


@pytest.mark.parametrize(
    "path",
    [
        # Documentation
        "docs/code_quality/index.rst",
        "browser/components/urlbar/docs/overview.md",
        "toolkit/components/README",
        "third_party/rust/serde/LICENSE-MIT",
        # Tests
        "dom/base/test/test_anchor.html",
        "dom/base/test/mochitest.toml",
        "dom/base/test/gtest/TestSomething.cpp",
        "dom/base/test/gtest/moz.build",
        "browser/components/tests/browser/browser_foo.js",
        "toolkit/components/places/tests/unit/xpcshell.toml",
        "layout/reftests/bugs/reftest.list",
        "layout/generic/crashtests/crashtests.list",
        "js/src/jit-test/tests/basic/foo.js",
        "js/src/jsapi-tests/testFoo.cpp",
        "testing/web-platform/meta/css/css-grid/foo.html.ini",
        "testing/web-platform/mozilla/meta/foo/bar.html.ini",
        "testing/web-platform/tests/css/css-grid/foo.html",
        "netwerk/protocol/http/test_foo.js",
        "python/mozbuild/mozbuild/test/python.toml",
        "security/manager/ssl/tests/unit/test_foo.js",
        "third_party/googletest/googletest/src/gtest.cc",
    ],
)
def test_unchanged_paths(path):
    assert is_unchanged_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "dom/base/nsDocument.cpp",
        "browser/components/urlbar/UrlbarInput.sys.mjs",
        "browser/themes/shared/urlbar.css",
        "toolkit/moz.build",
        # Test harnesses are code, not tests
        "testing/mozharness/configs/foo.py",
        "testing/marionette/client/foo.py",
        "testing/mozbase/mozprocess/mozprocess/processhandler.py",
        "python/mozbuild/mozbuild/frontend/reader.py",
        "taskcluster/kinds/build/kind.yml",
        "netwerk/protocol/http/nsHttpChannel.h",
        "docs.cpp",
        "licensed_foo.cpp",
        "readme_parser.py",
        "mach",
        "browser/locales/en-US/browser/browser.ftl",
    ],
)
def test_changed_paths(path):
    assert is_unchanged_path(path) is False


@pytest.mark.parametrize(
    "path",
    [
        "browser/themes/shared/urlbar.css",
        "browser/themes/shared/icons/back.svg",
        "browser/branding/official/default128.png",
        "toolkit/themes/shared/fonts/FiraSans.woff2",
        "browser/locales/en-US/browser/browser.ftl",
        "toolkit/locales/en-US/chrome/global/commonDialogs.properties",
        "browser/locales/en-US/chrome/browser/browser.dtd",
        "browser/branding/official/firefox.ico",
    ],
)
def test_ui_paths(path):
    assert is_ui_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "browser/components/urlbar/UrlbarInput.sys.mjs",
        "browser/base/content/browser.xhtml",
        "browser/base/content/browser.js",
        "dom/base/nsDocument.cpp",
        "browser/themes/shared/jar.mn",
        "browser/locales/l10n.toml",
    ],
)
def test_non_ui_paths(path):
    assert is_ui_path(path) is False


def test_detect_testing_exception_ui():
    # Only UI files
    assert (
        detect_testing_policy_tag(
            ["browser/themes/shared/urlbar.css", "browser/themes/shared/icons/back.svg"]
        )
        == TESTING_EXCEPTION_UI_PHID
    )

    # UI files along with documentation or tests
    assert (
        detect_testing_policy_tag(
            [
                "browser/locales/en-US/browser/browser.ftl",
                "docs/index.rst",
                "browser/components/tests/browser/browser_foo.js",
            ]
        )
        == TESTING_EXCEPTION_UI_PHID
    )

    # A single code file is enough to disable the heuristic
    assert (
        detect_testing_policy_tag(
            ["browser/themes/shared/urlbar.css", "browser/base/content/browser.js"]
        )
        is None
    )

    # UI files in a test directory are just tests
    assert (
        detect_testing_policy_tag(["browser/base/content/test/static/dummy.css"])
        == TESTING_EXCEPTION_UNCHANGED_PHID
    )


@pytest.mark.parametrize(
    "path, expected",
    [
        ("dom/base/test/test_anchor.html", True),
        ("browser/components/tests/browser/browser_foo.js", True),
        ("dom/base/test/gtest/TestSomething.cpp", True),
        ("testing/web-platform/tests/css/css-grid/foo.html", True),
        # Manifests and expectations
        ("dom/base/test/mochitest.toml", False),
        ("layout/reftests/bugs/reftest.list", False),
        ("testing/web-platform/meta/css/css-grid/foo.html.ini", False),
        # Not tests
        ("dom/base/nsDocument.cpp", False),
        ("docs/index.rst", False),
    ],
)
def test_is_test_file(path, expected):
    assert is_test_file(path) is expected


def test_detect_testing_approved():
    # Code changes along with test changes
    assert (
        detect_testing_policy_tag(
            ["dom/base/nsDocument.cpp", "dom/base/test/test_anchor.html"]
        )
        == TESTING_APPROVED_PHID
    )
    assert (
        detect_testing_policy_tag(
            [
                "browser/components/urlbar/UrlbarInput.sys.mjs",
                "browser/themes/shared/urlbar.css",
                "browser/components/urlbar/tests/browser/browser_foo.js",
                "docs/index.rst",
            ]
        )
        == TESTING_APPROVED_PHID
    )

    # Code changes without tests
    assert detect_testing_policy_tag(["dom/base/nsDocument.cpp"]) is None
    assert (
        detect_testing_policy_tag(["dom/base/nsDocument.cpp", "docs/index.rst"]) is None
    )

    # Only touching a manifest or expectations is not adding tests
    assert (
        detect_testing_policy_tag(
            ["dom/base/nsDocument.cpp", "dom/base/test/mochitest.toml"]
        )
        is None
    )
    assert (
        detect_testing_policy_tag(
            [
                "layout/style/nsCSSValue.cpp",
                "testing/web-platform/meta/css/css-grid/foo.html.ini",
            ]
        )
        is None
    )

    # Tests only are unchanged, not approved
    assert (
        detect_testing_policy_tag(["dom/base/test/test_anchor.html"])
        == TESTING_EXCEPTION_UNCHANGED_PHID
    )


def test_detect_testing_policy_tag():
    # All files are documentation or tests: unchanged
    assert (
        detect_testing_policy_tag(
            ["docs/index.rst", "dom/base/test/test_foo.html", "dom/base/test/moz.build"]
        )
        == TESTING_EXCEPTION_UNCHANGED_PHID
    )

    # A single code file is enough to disable the heuristic
    assert (
        detect_testing_policy_tag(["docs/index.rst", "dom/base/nsDocument.cpp"]) is None
    )

    # No files, no tag
    assert detect_testing_policy_tag([]) is None
    assert detect_testing_policy_tag({}.keys()) is None


@pytest.fixture
def api():
    mock = MagicMock()
    mock.request.side_effect = lambda path, **kwargs: {
        "transaction.search": {"data": []},
    }[path]
    return mock


@pytest.fixture
def revision():
    mock = MagicMock()
    mock.phabricator_id = REVISION_ID
    mock.phabricator_phid = REVISION_PHID
    mock.files = ["docs/index.rst", "dom/base/test/test_foo.html"]
    return mock


def _revision_data(project_phids):
    return {
        "fields": {"authorPHID": "PHID-USER-author"},
        "attachments": {"projects": {"projectPHIDs": project_phids}},
    }


def test_apply_tag(api, revision):
    """The tag is added when the revision has no testing policy tag"""
    api.load_revision.return_value = _revision_data([OTHER_PROJECT_PHID])

    assert apply_testing_policy_tag(api, revision) == TESTING_EXCEPTION_UNCHANGED_PHID

    api.load_revision.assert_called_once_with(
        rev_id=REVISION_ID, attachments={"projects": True}
    )
    api.edit_revision.assert_called_once_with(
        REVISION_ID,
        [{"type": "projects.add", "value": [TESTING_EXCEPTION_UNCHANGED_PHID]}],
    )


def test_apply_tag_no_projects(api, revision):
    """The tag is added when the revision has no project at all"""
    api.load_revision.return_value = _revision_data([])

    assert apply_testing_policy_tag(api, revision) == TESTING_EXCEPTION_UNCHANGED_PHID

    # Only the transactions were checked
    api.request.assert_called_once_with(
        "transaction.search", objectIdentifier=REVISION_PHID
    )
    api.edit_revision.assert_called_once()


def test_no_tag_for_code_changes(api, revision):
    """Nothing happens when the patch touches code"""
    revision.files = ["docs/index.rst", "dom/base/nsDocument.cpp"]

    assert apply_testing_policy_tag(api, revision) is None

    api.load_revision.assert_not_called()
    api.request.assert_not_called()
    api.edit_revision.assert_not_called()


def test_already_tagged_same_tag(api, revision):
    """Nothing happens when the tag is already set"""
    api.load_revision.return_value = _revision_data([TESTING_EXCEPTION_UNCHANGED_PHID])

    assert apply_testing_policy_tag(api, revision) is None

    api.request.assert_not_called()
    api.edit_revision.assert_not_called()


def test_already_tagged_other_testing_tag(api, revision):
    """Nothing happens when another testing policy tag was set by a human"""
    api.load_revision.return_value = _revision_data(
        [OTHER_PROJECT_PHID, TESTING_APPROVED_PHID]
    )

    assert apply_testing_policy_tag(api, revision) is None

    api.request.assert_not_called()
    api.edit_revision.assert_not_called()


def test_tag_previously_removed(api, revision):
    """The tag is not added again when someone removed it"""
    api.load_revision.return_value = _revision_data([])
    api.request.side_effect = lambda path, **kwargs: {
        "transaction.search": {
            "data": [
                {"type": "comment", "fields": {}},
                {
                    "type": "projects",
                    "fields": {
                        "operations": [
                            {
                                "operation": "add",
                                "phid": TESTING_EXCEPTION_UNCHANGED_PHID,
                            }
                        ]
                    },
                },
                {
                    "type": "projects",
                    "fields": {
                        "operations": [
                            {
                                "operation": "remove",
                                "phid": TESTING_EXCEPTION_UNCHANGED_PHID,
                            }
                        ]
                    },
                },
            ]
        },
    }[path]

    assert apply_testing_policy_tag(api, revision) is None

    api.request.assert_called_once_with(
        "transaction.search", objectIdentifier=REVISION_PHID
    )
    api.edit_revision.assert_not_called()


def test_api_failure_is_not_fatal(api, revision):
    """A Phabricator error must not break the publication"""
    api.load_revision.side_effect = Exception("Phabricator is down")

    assert apply_testing_policy_tag(api, revision) is None

    api.edit_revision.assert_not_called()


def test_phabricator_reporter_sets_tag(
    mock_phabricator, phab, mock_try_task, mock_decision_task, mock_backend_secret
):
    """
    The Phabricator reporter sets the tag on a documentation-only revision
    """
    from code_review_bot.report.phabricator import PhabricatorReporter
    from code_review_bot.revisions import Revision

    with mock_phabricator as api:
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)
        revision.lines = {"docs/index.rst": [1, 2], "dom/base/test/test_foo.html": [3]}
        revision.files = list(revision.lines.keys())
        revision.id = 52
        reporter = PhabricatorReporter({}, api=api)

    reporter.publish([], revision, [], [], [])

    # A single transaction adding the tag has been sent
    assert phab.transactions == {
        51: [[{"type": "projects.add", "value": [TESTING_EXCEPTION_UNCHANGED_PHID]}]]
    }


def test_phabricator_reporter_skips_code_changes(
    mock_phabricator, phab, mock_try_task, mock_decision_task, mock_backend_secret
):
    """
    The Phabricator reporter does not tag a revision modifying code
    """
    from code_review_bot.report.phabricator import PhabricatorReporter
    from code_review_bot.revisions import Revision

    with mock_phabricator as api:
        revision = Revision.from_try_task(mock_try_task, mock_decision_task, api)
        revision.lines = {"docs/index.rst": [1, 2], "dom/base/nsDocument.cpp": [3]}
        revision.files = list(revision.lines.keys())
        revision.id = 52
        reporter = PhabricatorReporter({}, api=api)

    reporter.publish([], revision, [], [], [])

    assert phab.transactions == {}
