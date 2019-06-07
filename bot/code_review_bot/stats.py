# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datadog

from static_analysis_bot.config import settings


class Datadog(object):
    '''
    Log metrics using Datadog REST api
    '''
    def __init__(self):
        self.api = datadog.ThreadStats()

    def auth(self, api_key):
        assert settings.app_channel is not None, \
            'Missing app channel'
        datadog.initialize(
            api_key=api_key,
            host_name='{}.code-review.allizom.org'.format(settings.app_channel),
        )
        self.api.constant_tags = [
            'code-review',
            'env:{}'.format(settings.app_channel),
        ]
        self.api.start(
            flush_in_thread=True,
        )
        assert not self.api._disabled

    def report_issues(self, name, issues):
        '''
        Aggregate statistics about found issues
        '''
        # Report all issues found
        self.api.increment(
            'issues.{}'.format(name),
            len(issues),
        )

        # Report publishable issues
        self.api.increment(
            'issues.{}.publishable'.format(name),
            sum(i.is_publishable() for i in issues),
        )
