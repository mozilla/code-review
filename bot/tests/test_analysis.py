# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from code_review_bot.config import RepositoryConf
from code_review_bot.revisions import Revision


def test_revision(mock_autoland_task, mock_phabricator, mock_hgmo):
    """
    Validate the creation of a Revision in analysis context
    using Phabricator webhook payload
    """

    with mock_phabricator as api:
        revision = Revision.from_phabricator_trigger(
            revision_phid="PHID-DREV-1234",
            transactions=[
                "PHID-XACT-aaaa",
            ],
            phabricator=api,
        )

    assert revision.as_dict() == {
        "base_changeset": "tip",
        "base_repository": "https://hg.mozilla.org/mozilla-central",
        "bugzilla_id": 1234567,
        "diff_id": 42,
        "diff_phid": "PHID-DIFF-test",
        "has_clang_files": False,
        "head_changeset": None,
        "head_repository": None,
        "id": 51,
        "mercurial_revision": None,
        "phid": "PHID-DREV-1234",
        "repository": None,
        "target_repository": "https://hg.mozilla.org/mozilla-central",
        "title": "Static Analysis tests",
        "url": "https://phabricator.test/D51",
    }
    assert revision.build_target_phid == "PHID-HMBT-test"
    assert revision.phabricator_phid == "PHID-DREV-1234"
    assert revision.base_repository_conf == RepositoryConf(
        name="mozilla-central",
        try_name="try",
        url="https://hg.mozilla.org/mozilla-central",
        try_url="ssh://hg.mozilla.org/try",
        decision_env_prefix="GECKO",
        ssh_user="reviewbot@mozilla.com",
    )
    assert revision.repository_try_name == "try"
