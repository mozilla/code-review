# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import atexit
import time
from contextlib import contextmanager
from datetime import datetime

import structlog
from influxdb import InfluxDBClient

from code_review_bot.config import settings
from code_review_bot.tasks.base import AnalysisTask

logger = structlog.get_logger(__name__)


class InfluxDb(object):
    """
    Log metrics using InfluxDb REST api
    """

    def __init__(self):
        self.client = None
        self.metrics = []

        # Always flush at the end of the execution
        atexit.register(self.flush)

    def auth(self, conf):
        assert settings.app_channel is not None, "Missing app channel"
        self.client = InfluxDBClient(
            conf["host"],
            conf["port"],
            conf["username"],
            conf["password"],
            conf["database"],
            ssl=conf.get("ssl", False),
            verify_ssl=conf.get("ssl", False),
        )
        assert self.client.ping()
        logger.info(
            "InfluxDb reporting enabled", database=conf["database"], host=conf["host"]
        )

    def add_metric(self, name, value=1, tags={}):
        """
        Store a metric in memory, using InfluxDb point format
        """
        tags.update({"app": "code-review-bot", "channel": settings.app_channel})
        self.metrics.append(
            {
                "measurement": f"code-review.{name}",
                "tags": tags,
                "time": datetime.utcnow().isoformat(),
                "fields": {"value": value},
            }
        )

    def flush(self):
        """
        Publish all metrics in memory to influxdb
        """
        if self.client is None:
            logger.warning(
                "InfluxDb client not connected: metrics will not be reported"
            )
            return
        if not self.metrics:
            return

        logger.info("Flushing stats metrics", nb=len(self.metrics))
        # TODO: add a retry ?
        self.client.write_points(self.metrics)
        self.metrics = []

    def report_task(self, task, issues):
        """
        Aggregate statistics about issues from a remote analysis task
        """
        assert isinstance(task, AnalysisTask)
        tags = {"task": task.name}

        # Report all issues found
        self.add_metric("issues", len(issues), tags)

        # Report publishable issues
        self.add_metric(
            "issues.publishable", sum(i.is_publishable() for i in issues), tags
        )

        # Report total paths
        self.add_metric("issues.paths", len({i.path for i in issues}), tags)

    @contextmanager
    def timer(self, name):
        """
        A context manager tracking the contained code's runtime
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            end = time.perf_counter()
            self.add_metric(name, end - start)
