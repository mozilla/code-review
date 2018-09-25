# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import

import enum
import os
import tempfile

import requests
import yaml

from cli_common.log import get_logger

PROJECT_NAME = 'static-analysis-bot'
CONFIG_URL = 'https://hg.mozilla.org/mozilla-central/raw-file/tip/tools/clang-tidy/config.yaml'
REPO_CENTRAL = b'https://hg.mozilla.org/mozilla-central'
REPO_UNIFIED = b'https://hg.mozilla.org/mozilla-unified'
ARTIFACT_URL = 'https://queue.taskcluster.net/v1/task/{task_id}/runs/{run_id}/artifacts/public/results/{diff_name}'


logger = get_logger(__name__)


class Publication(enum.Enum):
    # Only check if the issue is in the developer patch
    # This is the original mode
    IN_PATCH = 1

    # Every new issue (not found before applying the patch)
    # will be published
    BEFORE_AFTER = 2


class Settings(object):
    def __init__(self):
        self.config = None
        self.app_channel = None
        self.publication = None

        # Paths
        self.cache_root = None
        self.repo_dir = None
        self.repo_shared_dir = None
        self.taskcluster_results_dir = None

    def setup(self, app_channel, cache_root, publication):
        self.app_channel = app_channel
        self.download({
            'cpp_extensions': frozenset(['.c', '.h', '.cpp', '.cc', '.cxx', '.hh', '.hpp', '.hxx', '.m', '.mm']),
            'java_extensions': frozenset(['.java']),
        })
        assert 'clang_checkers' in self.config
        assert 'target' in self.config

        assert isinstance(publication, str)
        try:
            self.publication = Publication[publication]
        except KeyError:
            raise Exception('Publication mode should be {}'.format('|'.join(map(lambda p: p .name, Publication))))

        assert os.path.isdir(cache_root)
        self.cache_root = cache_root
        self.repo_dir = os.path.join(self.cache_root, 'sa-unified')
        self.repo_shared_dir = os.path.join(self.cache_root, 'sa-unified-shared')

        if 'TASK_ID' in os.environ and 'RUN_ID' in os.environ:
            self.taskcluster_results_dir = '/tmp/results'
        else:
            self.taskcluster_results_dir = tempfile.mkdtemp()
        if not os.path.isdir(self.taskcluster_results_dir):
            os.makedirs(self.taskcluster_results_dir)

    def __getattr__(self, key):
        if key not in self.config:
            raise AttributeError
        return self.config[key]

    def download(self, defaults={}):
        '''
        Configuration is stored on mozilla central
        It has to be downloaded on each run
        '''
        assert isinstance(defaults, dict)
        assert self.config is None, \
            'Config already set.'
        resp = requests.get(CONFIG_URL)
        assert resp.ok, \
            'Failed to retrieve configuration from mozilla-central #{}'.format(resp.status_code)  # noqa

        self.config = defaults
        self.config.update(yaml.load(resp.content))
        logger.info('Loaded configuration from mozilla-central')

    def is_publishable_check(self, check):
        '''
        Is this check publishable ?
        Support the wildcard expansion
        Publication is enabled by default, even when missing
        '''
        if check is None:
            return False

        for c in self.clang_checkers:
            name = c['name']

            if name.endswith('*') and check.startswith(name[:-1]):
                # Wildcard at end of check name
                return c.get('publish', True)

            elif name == check:
                # Same exact check name
                return c.get('publish', True)

        return False


# Shared instance
settings = Settings()
