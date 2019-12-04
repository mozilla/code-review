# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from code_review_bot.revisions import Revision


def test_revision(mock_autoland_task, mock_phabricator, mock_hgmo):
    """
    Validate the creation of an autoland Revision
    """

    with mock_phabricator as api:
        revision = Revision.from_autoland(mock_autoland_task, api)

    assert revision.as_dict() == {
        "bugzilla_id": 1234567,
        "diff_id": 1,
        "diff_phid": "PHID-DIFF-autoland",
        "has_clang_files": False,
        "id": 123,
        "mercurial_revision": "deadbeef123",
        "phid": "PHID-DREV-azcDeadbeef",
        "repository": "https://hg.mozilla.org/integration/autoland",
        "target_repository": "https://hg.mozilla.org/mozilla-central",
        "title": "Static Analysis tests",
        "url": "https://phabricator.services.mozilla.com/D123",
    }
