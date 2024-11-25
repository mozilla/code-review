# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import rs_parsepatch


def test_phabricator(mock_config, mock_revision):
    """
    Test a phabricator revision
    """
    assert not hasattr(mock_revision, "mercurial")
    assert mock_revision.diff_id == 42
    assert mock_revision.diff_phid == "PHID-DIFF-test"
    assert mock_revision.url == "https://phabricator.test/D51"
    assert repr(mock_revision) == "PHID-DIFF-test"
    assert mock_revision.phabricator_id == 51

    # Patch is automatically loaded from Phabricator
    assert mock_revision.patch is not None
    assert isinstance(mock_revision.patch, str)
    assert len(mock_revision.patch.split("\n")) == 15
    patch = rs_parsepatch.get_diffs(mock_revision.patch)
    assert patch == [
        {
            "binary": False,
            "copied_from": None,
            "deleted": False,
            "filename": "test.txt",
            "lines": [(1, 1, b"Hello World"), (None, 2, b"Second line")],
            "modes": {},
            "new": False,
            "renamed_from": None,
        },
        {
            "binary": False,
            "copied_from": None,
            "deleted": False,
            "filename": "test.cpp",
            "lines": [(None, 1, b"Hello World")],
            "modes": {"new": 33188},
            "new": True,
            "renamed_from": None,
        },
    ]
    patch = rs_parsepatch.get_lines(mock_revision.patch)
    assert patch == [
        {
            "added_lines": [2],
            "binary": False,
            "copied_from": None,
            "deleted": False,
            "deleted_lines": [],
            "filename": "test.txt",
            "modes": {},
            "new": False,
            "renamed_from": None,
        },
        {
            "added_lines": [1],
            "binary": False,
            "copied_from": None,
            "deleted": False,
            "deleted_lines": [],
            "filename": "test.cpp",
            "modes": {"new": 33188},
            "new": True,
            "renamed_from": None,
        },
    ]


def test_autoland(mock_config, mock_revision_autoland):
    """
    Test a revision coming from a decision task (meaning autoland)
    """
    assert mock_revision_autoland.diff_id is None
    assert mock_revision_autoland.diff_phid is None
    assert mock_revision_autoland.url is None
    assert (
        mock_revision_autoland.head_repository
        == "https://hg.mozilla.org/integration/autoland"
    )
    assert mock_revision_autoland.head_changeset == "deadbeef123"
    assert (
        mock_revision_autoland.base_repository
        == "https://hg.mozilla.org/mozilla-unified"
    )
    assert mock_revision_autoland.base_changeset == "123deadbeef"

    assert (
        repr(mock_revision_autoland)
        == "deadbeef123@https://hg.mozilla.org/integration/autoland"
    )


def test_clang_files(mock_revision):
    """
    Test clang files detection
    """
    assert mock_revision.files == []
    assert not mock_revision.has_clang_files

    mock_revision.files = ["test.cpp", "test.h"]
    assert mock_revision.has_clang_files

    mock_revision.files = ["test.py", "test.js"]
    assert not mock_revision.has_clang_files

    mock_revision.files = ["test.cpp", "test.js", "xxx.txt"]
    assert mock_revision.has_clang_files

    mock_revision.files = ["test.h", "test.js", "xxx.txt"]
    assert not mock_revision.has_clang_files

    assert mock_revision.has_clang_header_files


def test_analyze_patch(mock_revision):
    from code_review_bot import Issue

    class MyIssue(Issue):
        def __init__(self, path, line):
            self.path = path
            self.line = line
            self.nb_lines = 1

        def as_dict():
            return {}

        def as_markdown():
            return ""

        def as_text():
            return ""

        def validates():
            return True

        def as_phabricator_lint():
            return {}

    issue_in_new_file = MyIssue("new.txt", 1)
    issue_in_existing_file_touched_line = MyIssue("modified.txt", 3)
    issue_in_existing_file_not_changed_line = MyIssue("modified.txt", 1)
    issue_in_existing_file_added_line = MyIssue("added.txt", 4)
    issue_in_not_changed_file = MyIssue("notexisting.txt", 1)
    issue_full_file = MyIssue("new.txt", None)

    mock_revision.patch = """
diff --git a/new.txt b/new.txt
new file mode 100644
index 00000000..83db48f8
--- /dev/null
+++ b/new.txt
@@ -0,0 +1,3 @@
+line1
+line2
+line3
diff --git a/modified.txt b/modified.txt
index 84275f99..cbc9b72a 100644
--- a/modified.txt
+++ b/modified.txt
@@ -1,4 +1,4 @@
 line1
 line2
-line3
+line7
 line4
diff --git a/added.txt b/added.txt
index 83db48f8..84275f99 100644
--- a/added.txt
+++ b/added.txt
@@ -1,3 +1,4 @@
 line1
 line2
 line3
+line4
"""

    mock_revision.analyze_patch()
    assert "new.txt" in mock_revision.lines
    assert mock_revision.lines["new.txt"] == [1, 2, 3]
    assert "modified.txt" in mock_revision.lines
    assert mock_revision.lines["modified.txt"] == [3]
    assert "added.txt" in mock_revision.lines
    assert mock_revision.lines["added.txt"] == [4]
    assert "new.txt" in mock_revision.files
    assert "modified.txt" in mock_revision.files
    assert "added.txt" in mock_revision.files

    assert mock_revision.has_file("new.txt")
    assert mock_revision.has_file("modified.txt")
    assert mock_revision.has_file("added.txt")
    assert not mock_revision.has_file("notexisting.txt")

    assert mock_revision.contains(issue_in_new_file)
    assert mock_revision.contains(issue_in_existing_file_touched_line)
    assert not mock_revision.contains(issue_in_existing_file_not_changed_line)
    assert mock_revision.contains(issue_in_existing_file_added_line)
    assert not mock_revision.contains(issue_in_not_changed_file)
    assert mock_revision.contains(issue_full_file)


def test_bugzilla_id(mock_revision):
    """Test the bugzilla id parsing from phabricator data"""

    # Default value from mock
    assert mock_revision.bugzilla_id == 1234567

    # Update phabricator data on revision
    mock_revision.revision["fields"]["bugzilla.bug-id"] = "456789"
    assert mock_revision.bugzilla_id == 456789

    # On bad data fallback gracefully
    mock_revision.revision["fields"]["bugzilla.bug-id"] = "notaBZid"
    assert mock_revision.bugzilla_id is None

    # On missing data fallback gracefully
    del mock_revision.revision["fields"]["bugzilla.bug-id"]
    assert mock_revision.bugzilla_id is None


def test_revision_before_after(mock_config, mock_revision, mock_taskcluster_config):
    """
    Ensure before/after feature is always run on specific revisions
    """
    mock_taskcluster_config.secrets["BEFORE_AFTER_RATIO"] = 0.5
    mock_revision.id = 51
    assert mock_revision.before_after_feature is True
    mock_revision.id = 42
    assert mock_revision.before_after_feature is False
