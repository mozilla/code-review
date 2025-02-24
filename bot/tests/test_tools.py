# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest
from taskcluster.helper import TaskclusterConfig

from code_review_bot.tools.log import remove_color_codes


def test_taskcluster_service():
    """
    Test taskcluster service loader
    """
    taskcluster = TaskclusterConfig("http://tc.test")

    assert taskcluster.get_service("secrets") is not None
    assert taskcluster.get_service("hooks") is not None
    assert taskcluster.get_service("index") is not None
    with pytest.raises(AssertionError) as e:
        taskcluster.get_service("nope")
    assert str(e.value) == "Invalid Taskcluster service nope"


def test_remove_color_codes(sentry_event_with_colors, sentry_event_without_colors):
    """
    Test the removal of color codes from Sentry payloads
    """
    assert (
        remove_color_codes(sentry_event_with_colors, hint=None)
        == sentry_event_without_colors
    )
