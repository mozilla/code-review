# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from __future__ import absolute_import

import collections
import enum
import fnmatch
import os
import tempfile

import requests
import yaml

from cli_common.log import get_logger

PROJECT_NAME = 'static-analysis-bot'
CONFIG_URL = 'https://hg.mozilla.org/mozilla-central/raw-file/tip/tools/clang-tidy/config.yaml'
REPO_CENTRAL = b'https://hg.mozilla.org/mozilla-central'
REPO_UNIFIED = b'https://hg.mozilla.org/mozilla-unified'


logger = get_logger(__name__)

TaskCluster = collections.namedtuple('TaskCluster', 'results_dir, task_id, run_id, local')


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
        self.taskcluster = None

    def setup(self, app_channel, cache_root, publication, allowed_paths):
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

        # Save Taskcluster ID for logging
        if 'TASK_ID' in os.environ and 'RUN_ID' in os.environ:
            self.taskcluster = TaskCluster('/tmp/results', os.environ['TASK_ID'], os.environ['RUN_ID'], False)
        else:
            self.taskcluster = TaskCluster(tempfile.mkdtemp(), 'local instance', 0, True)
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

        clang_check = self.get_clang_check(check)
        return clang_check.get('publish', True) if clang_check else False

    def is_allowed_path(self, path):
        '''
        Is this path allowed for reporting ?
        '''
        return any([
            fnmatch.fnmatch(path, rule)
            for rule in self.allowed_paths
        ])

    def get_clang_check(self, check):

        if check is None:
            return None

        for c in self.clang_checkers:
            name = c['name']

            if name.endswith('*') and check.startswith(name[:-1]):
                # Wildcard at end of check name
                return c

            elif name == check:
                # Same exact check name
                return c

        return None


# Shared instance
settings = Settings()
