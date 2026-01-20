# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from code_review_bot.revisions import PhabricatorRevision


def test_revision(mock_autoland_task, mock_phabricator, mock_hgmo):
    """
    Validate the creation of an autoland Revision
    """

    with mock_phabricator as api:
        revision = PhabricatorRevision.from_decision_task(mock_autoland_task, api)

    assert revision.as_dict() == {
        "bugzilla_id": None,
        "diff_id": None,
        "diff_phid": None,
        "has_clang_files": False,
        "id": None,
        "mercurial_revision": "deadbeef123",
        "phid": None,
        "repository": "https://hg.mozilla.org/integration/autoland",
        "target_repository": "https://hg.mozilla.org/mozilla-unified",
        "title": "Changeset deadbeef123 (https://hg.mozilla.org/integration/autoland)",
        "url": None,
        "head_repository": "https://hg.mozilla.org/integration/autoland",
        "base_repository": "https://hg.mozilla.org/mozilla-unified",
        "head_changeset": "deadbeef123",
        "base_changeset": "123deadbeef",
    }
