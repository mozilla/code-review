# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import

import atexit
import collections
import fnmatch
import os
import re
import shutil
import tempfile

import structlog

REPO_MOZILLA_CENTRAL = "https://hg.mozilla.org/mozilla-central"
REPO_AUTOLAND = "https://hg.mozilla.org/integration/autoland"
REGEX_PHABRICATOR_COMMIT = re.compile(
    r"^Differential Revision: (https://[\w\-\.]+/D(\d+))$", re.MULTILINE
)

logger = structlog.get_logger(__name__)

TaskCluster = collections.namedtuple(
    "TaskCluster", "results_dir, task_id, run_id, local"
)
RepositoryConf = collections.namedtuple(
    "RepositoryConf", "url, decision_env_revision, decision_env_repository"
)


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
        self.taskcluster = None
        self.try_task_id = None
        self.try_group_id = None
        self.autoland_group_id = None
        self.hgmo_cache = tempfile.mkdtemp(suffix="hgmo")
        self.repositories = []

        # Always cleanup at the end of the execution
        atexit.register(self.cleanup)

    def setup(self, app_channel, allowed_paths, repositories):
        # Detect source from env
        if "TRY_TASK_ID" in os.environ and "TRY_TASK_GROUP_ID" in os.environ:
            self.try_task_id = os.environ["TRY_TASK_ID"]
            self.try_group_id = os.environ["TRY_TASK_GROUP_ID"]
        elif "AUTOLAND_TASK_GROUP_ID" in os.environ:
            self.autoland_group_id = os.environ["AUTOLAND_TASK_GROUP_ID"]
        else:
            raise Exception("Only TRY mode is supported")

        self.app_channel = app_channel

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

        # Build available repositories from secret
        def build_conf(nb, repo):
            assert isinstance(
                repo, dict
            ), "Repository configuration #{nb+1} is not a dict"
            data = []
            for key in RepositoryConf._fields:
                assert (
                    key in repo
                ), f"Missing key {key} in repository configuration #{nb+1}"
                data.append(repo[key])
            return RepositoryConf._make(data)

        self.repositories = [build_conf(i, repo) for i, repo in enumerate(repositories)]
        assert self.repositories, "No repositories available"

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
