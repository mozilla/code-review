# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from datetime import datetime

from code_review_bot import stats


class MockInflux:
    """
    Mock the InfluxDb python client to retrieve data sent
    """

    points = []

    def write_points(self, points):
        self.points += points


def test_base_stats():
    """
    Test simple stat management
    """
    # Reset stats
    stats.metrics = []

    stats.add_metric("test.a.b.c", 12)

    assert len(stats.metrics) == 1
    metric = stats.metrics[0]
    assert metric["fields"] == {"value": 12}
    assert metric["measurement"] == "code-review.test.a.b.c"
    assert metric["tags"] == {"app": "code-review-bot", "channel": "test"}
    assert datetime.strptime(metric["time"], "%Y-%m-%dT%H:%M:%S.%f")

    # Flush without client does not do anything (no crash)
    stats.flush()
    assert len(stats.metrics) == 1

    # Point are sent on flush
    stats.client = MockInflux()
    assert len(stats.client.points) == 0
    stats.flush()
    assert len(stats.metrics) == 0
    assert len(stats.client.points) == 1
