# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import

import atexit
import collections
import enum
import fnmatch
import os
import shutil
import tempfile

import structlog

PROJECT_NAME = "code-review-bot"

logger = structlog.get_logger(__name__)

TaskCluster = collections.namedtuple(
    "TaskCluster", "results_dir, task_id, run_id, local"
)


class Publication(enum.Enum):
    # Only check if the issue is in the developer patch
    # This is the original mode
    IN_PATCH = 1

    # Every new issue (not found before applying the patch)
    # will be published
    BEFORE_AFTER = 2


class Settings(object):
    def __init__(self):
        self.config = {
            "cpp_extensions": frozenset([".c", ".cpp", ".cc", ".cxx", ".m", ".mm"]),
            "cpp_header_extensions": frozenset([".h", ".hh", ".hpp", ".hxx"]),
            "java_extensions": frozenset([".java"]),
            "idl_extensions": frozenset([".idl"]),
            "js_extensions": frozenset([".js", ".jsm"]),
        }
        self.app_channel = None
        self.publication = None
        self.taskcluster = None
        self.try_task_id = None
        self.try_group_id = None
        self.hgmo_cache = tempfile.mkdtemp(suffix="hgmo")

        # Always cleanup at the end of the execution
        atexit.register(self.cleanup)

    def setup(self, app_channel, publication, allowed_paths):
        # Detect source from env
        if "TRY_TASK_ID" in os.environ and "TRY_TASK_GROUP_ID" in os.environ:
            self.try_task_id = os.environ["TRY_TASK_ID"]
            self.try_group_id = os.environ["TRY_TASK_GROUP_ID"]
        else:
            raise Exception("Only TRY mode is supported")

        self.app_channel = app_channel

        assert isinstance(publication, str)
        try:
            self.publication = Publication[publication]
        except KeyError:
            raise Exception(
                "Publication mode should be {}".format(
                    "|".join(map(lambda p: p.name, Publication))
                )
            )

        # Save Taskcluster ID for logging
        if "TASK_ID" in os.environ and "RUN_ID" in os.environ:
            self.taskcluster = TaskCluster(
                "/tmp/results", os.environ["TASK_ID"], os.environ["RUN_ID"], False
            )
        else:
            self.taskcluster = TaskCluster(
                tempfile.mkdtemp(), "local instance", 0, True
            )
        if not os.path.isdir(self.taskcluster.results_dir):
            os.makedirs(self.taskcluster.results_dir)

        # Save allowed paths
        assert isinstance(allowed_paths, list)
        assert all(map(lambda p: isinstance(p, str), allowed_paths))
        self.allowed_paths = allowed_paths

    def __getattr__(self, key):
        if key not in self.config:
            raise AttributeError
        return self.config[key]

    @property
    def on_production(self):
        """
        Are we running on production ?
        """
        return self.app_channel == "production" and self.taskcluster.local is False

    def is_allowed_path(self, path):
        """
        Is this path allowed for reporting ?
        """
        return any([fnmatch.fnmatch(path, rule) for rule in self.allowed_paths])

    def cleanup(self):
        shutil.rmtree(self.hgmo_cache)


# Shared instance
settings = Settings()
