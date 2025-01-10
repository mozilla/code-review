# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.


import atexit
import collections
import fnmatch
import json
import os
import shutil
import tempfile
from pathlib import Path

import pkg_resources
import structlog

REPO_MOZILLA_CENTRAL = "https://hg.mozilla.org/mozilla-central"
REPO_AUTOLAND = "https://hg.mozilla.org/integration/autoland"

logger = structlog.get_logger(__name__)

TaskCluster = collections.namedtuple(
    "TaskCluster", "results_dir, task_id, run_id, local"
)
RepositoryConf = collections.namedtuple(
    "RepositoryConf",
    "name, try_name, url, try_url, decision_env_prefix, ssh_user",
)


def GetAppUserAgent():
    return {"user-agent": f"code-review-bot/{settings.version}"}


class Settings:
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
        self.mozilla_central_group_id = None
        self.phabricator_revision_phid = None
        self.phabricator_transactions = None
        self.repositories = []
        self.decision_env_prefixes = []

        # Max number of issues published to the backend at a time during the ingestion of a revision
        self.bulk_issue_chunks = 100

        # Cache to store file-by-file from HGMO Rest API
        self.hgmo_cache = tempfile.mkdtemp(suffix="hgmo")

        # Cache to store whole repositories
        self.mercurial_cache = None

        # SSH Key used to push on try
        self.ssh_key = None

        # Always cleanup at the end of the execution
        atexit.register(self.cleanup)
        # caching the versions of the app
        self.version = pkg_resources.require("code-review-bot")[0].version

    def setup(
        self,
        app_channel,
        allowed_paths,
        repositories,
        ssh_key=None,
        mercurial_cache=None,
    ):
        # Detect source from env
        if "TRY_TASK_ID" in os.environ and "TRY_TASK_GROUP_ID" in os.environ:
            self.try_task_id = os.environ["TRY_TASK_ID"]
            self.try_group_id = os.environ["TRY_TASK_GROUP_ID"]
        elif "AUTOLAND_TASK_GROUP_ID" in os.environ:
            self.autoland_group_id = os.environ["AUTOLAND_TASK_GROUP_ID"]
        elif "MOZILLA_CENTRAL_TASK_GROUP_ID" in os.environ:
            self.mozilla_central_group_id = os.environ["MOZILLA_CENTRAL_TASK_GROUP_ID"]
        elif (
            "PHABRICATOR_OBJECT_PHID" in os.environ
            and "PHABRICATOR_TRANSACTIONS" in os.environ
        ):
            # Setup trigger mode using Phabricator information
            self.phabricator_revision_phid = os.environ["PHABRICATOR_OBJECT_PHID"]
            assert self.phabricator_revision_phid.startswith(
                "PHID-DREV"
            ), f"Not a phabrication revision PHID: {self.phabricator_revision_phid}"
            try:
                self.phabricator_transactions = json.loads(
                    os.environ["PHABRICATOR_TRANSACTIONS"]
                )
            except Exception as e:
                logger.error("Failed to parse phabricator transactions", err=str(e))
                raise
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

        if "BULK_ISSUE_CHUNKS" in os.environ:
            self.bulk_issue_chunks = int(os.environ["BULK_ISSUE_CHUNKS"])

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

        # Save prefixes for decision environment variables
        self.decision_env_prefixes = [
            repo.decision_env_prefix for repo in self.repositories
        ]

        # Store mercurial cache path
        if mercurial_cache is not None:
            self.mercurial_cache = Path(mercurial_cache)
            assert (
                self.mercurial_cache.exists()
            ), f"Mercurial cache does not exist {self.mercurial_cache}"
            logger.info("Using mercurial cache", path=self.mercurial_cache)

            # Save ssh key when mercurial cache is enabled
            self.ssh_key = ssh_key

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

    @property
    def mercurial_cache_checkout(self):
        """
        When local mercurial cache is enabled, path to the checkout
        """
        if self.mercurial_cache is None:
            return
        return self.mercurial_cache / "checkout"

    @property
    def mercurial_cache_sharebase(self):
        """
        When local mercurial cache is enabled, path to the shared folder for robust checkout
        """
        if self.mercurial_cache is None:
            return
        return self.mercurial_cache / "shared"

    def is_allowed_path(self, path):
        """
        Is this path allowed for reporting ?
        """
        return any([fnmatch.fnmatch(path, rule) for rule in self.allowed_paths])

    def cleanup(self):
        shutil.rmtree(self.hgmo_cache)


# Shared instance
settings = Settings()
