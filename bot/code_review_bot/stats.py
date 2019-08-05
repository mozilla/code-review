# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import datadog

from code_review_bot.config import settings
from code_review_bot.tasks.base import AnalysisTask


class Datadog(object):
    """
    Log metrics using Datadog REST api
    """

    def __init__(self):
        self.api = datadog.ThreadStats()

    def auth(self, api_key):
        assert settings.app_channel is not None, "Missing app channel"
        datadog.initialize(
            api_key=api_key,
            host_name="{}.code-review.allizom.org".format(settings.app_channel),
        )
        self.api.constant_tags = ["code-review", "env:{}".format(settings.app_channel)]
        self.api.start(flush_in_thread=True)
        assert not self.api._disabled

    def report_task(self, task, issues):
        """
        Aggregate statistics about issues from a remote analysis task
        """
        assert isinstance(task, AnalysisTask)

        # Report all issues found
        self.api.increment("issues.{}".format(task.name), len(issues))

        # Report publishable issues
        self.api.increment(
            "issues.{}.publishable".format(task.name),
            sum(i.is_publishable() for i in issues),
        )

        # Report total paths
        self.api.increment(
            "issues.{}.paths".format(task.name), len({i.path for i in issues})
        )

        # Report cleaned paths
        self.api.increment(
            "issues.{}.cleaned_paths".format(task.name), len(task.cleaned_paths)
        )
