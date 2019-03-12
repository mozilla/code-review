# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import io
import os
import tarfile

import requests

import cli_common.log
import cli_common.utils
from static_analysis_bot import AnalysisException
from static_analysis_bot import stats
from static_analysis_bot.config import settings

logger = cli_common.log.get_logger(__name__)

COVERITY_CONFIG = '''
  {
    "type": "Coverity configuration",
    "format_version": 1,
    "settings": {
      "server": {
        "host": "%s",
        "ssl" : true,
        "on_new_cert" : "trust",
        "auth_key_file": "%s"
      },
      "stream": "Firefox",
      "cov_run_desktop": {
        "build_cmd": [],
        "clean_cmd": []
      }
    }
  }
'''


@stats.api.timed('runtime.coverity.setup')
def setup(index):
    '''
    Setup Taskcluster Coverity build for static-analysis
    '''
    assert settings.cov_url, 'Missing secret COVERITY_CONFIG:server_url'
    assert settings.cov_analysis_url, 'Missing secret COVERITY_CONFIG:package_url'
    assert settings.cov_auth, 'Missing secret COVERITY_CONFIG:auth_key'

    target = os.path.join(
        os.environ['MOZBUILD_STATE_PATH'], 'coverity')

    # Generate the coverity.conf and auth files
    cov_auth_path = os.path.join(target, 'auth')
    cov_setup_path = os.path.join(target, 'coverity.conf')
    cov_conf = COVERITY_CONFIG % (settings.cov_url, cov_auth_path)

    logger.info('Downloading from {}.'.format(settings.cov_analysis_url))
    cli_common.utils.retry(lambda: download(settings.cov_analysis_url, target))
    if not os.path.exists(target):
        raise AnalysisException('artifact', 'Setup failed for {}'.format(target))

    with open(cov_auth_path, 'w') as f:
        f.write(settings.cov_auth)

    # Modify it's permission to 600
    os.chmod(cov_auth_path, 0o600)

    with open(cov_setup_path, 'a') as f:
        f.write(cov_conf)


def download(artifact_url, target):
    # Download Taskcluster archive
    resp = requests.get(artifact_url, verify=False, stream=True)
    resp.raise_for_status()

    # Extract archive into destination
    with tarfile.open(fileobj=io.BytesIO(resp.content)) as tar:
        tar.extractall(target)
