# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import time


def test_base_stats(mock_stats):
    '''
    Test simple stat management
    '''
    mock_stats.api.event('Test Event', 'Dummy text...')
    mock_stats.api.increment('test.a.b.c', 12)

    mock_stats.flush()
    assert mock_stats.events == [
        {'text': 'Dummy text...', 'title': 'Test Event', 'tags': ['code-review', 'env:test', ]}
    ]
    metrics = mock_stats.get_metrics('test.a.b.c')
    assert len(metrics) == 1
    assert metrics[0][0] < time.time()
    assert metrics[0][1] == 12
