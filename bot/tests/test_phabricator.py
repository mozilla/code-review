# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import time
from unittest.mock import Mock

from conftest import MockBuild

from code_review_bot.sources.phabricator import PhabricatorBuildState


def test_backoff(PhabricatorMock):
    """
    Test update_state behaviour on retries
    """
    build = MockBuild(1234, "PHID-REPO-mc", 5678, "PHID-HMBT-deadbeef", {})
    build.state = PhabricatorBuildState.Queued

    with PhabricatorMock as phab:
        # Lower the max time to sleep to keep a speedy test
        phab.sleep = 0.1

        # The revision will be visible at the 3 try
        phab.is_visible = Mock(side_effect=[False, False, True])

        # Will stay queued as private
        phab.update_state(build)
        assert build.state == PhabricatorBuildState.Queued
        assert phab.is_visible.call_count == 1

        # After a short sleep, no update is triggered
        time.sleep(0.1)
        phab.update_state(build)
        assert build.state == PhabricatorBuildState.Queued
        assert phab.is_visible.call_count == 1

        # We need to still wait to get the next iteration
        time.sleep(0.3)
        phab.update_state(build)
        assert build.state == PhabricatorBuildState.Queued
        assert phab.is_visible.call_count == 2

        # Last iteration is even further away
        time.sleep(0.1)
        phab.update_state(build)
        assert build.state == PhabricatorBuildState.Queued
        assert phab.is_visible.call_count == 2

        # Finally it's public
        time.sleep(0.4)
        phab.update_state(build)
        assert build.state == PhabricatorBuildState.Public
        assert phab.is_visible.call_count == 3
