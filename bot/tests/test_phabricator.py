# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from unittest.mock import Mock

from conftest import MockBuild

from code_review_bot.sources.phabricator import PhabricatorBuildState


def test_update_state(PhabricatorMock):
    """
    Test update_state checks the visibility once
    """
    with PhabricatorMock as phab:
        phab.is_expired_build = Mock(return_value=False)

        # A visible revision is public
        build = MockBuild(1234, "PHID-REPO-mc", 5678, "PHID-HMBT-deadbeef", {})
        build.state = PhabricatorBuildState.Queued
        phab.is_visible = Mock(return_value=True)
        phab.update_state(build)
        assert build.state == PhabricatorBuildState.Public
        assert phab.is_visible.call_count == 1

        # A non visible revision is secured
        build = MockBuild(1234, "PHID-REPO-mc", 5678, "PHID-HMBT-deadbeef", {})
        build.state = PhabricatorBuildState.Queued
        phab.is_visible = Mock(return_value=False)
        phab.update_state(build)
        assert build.state == PhabricatorBuildState.Secured
        assert phab.is_visible.call_count == 1
