# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import tarfile
import requests
import io
import os
import cli_common.utils


def setup(product='static-analysis', job_name='linux64-clang-tidy', revision='latest', artifact='public/build/clang-tidy.tar.xz'):
    '''
    Setup Taskcluster clang build for static-analysis
    Defaults values are from https://dxr.mozilla.org/mozilla-central/source/taskcluster/ci/toolchain/linux.yml
    - Download the artifact from latest Taskcluster build
    - Extracts it into the MOZBUILD_STATE_PATH as expected by mach
    '''
    namespace = 'gecko.v2.mozilla-central.{}.{}.{}'.format(revision, product, job_name)
    artifact_url = 'https://index.taskcluster.net/v1/task/{}/artifacts/{}'.format(namespace, artifact)

    # Mach expects clang binaries in this specific root dir
    target = os.path.join(
        os.environ['MOZBUILD_STATE_PATH'],
        'clang-tools',
    )

    def _download():
        # Download Taskcluster archive
        resp = requests.get(artifact_url, stream=True)
        resp.raise_for_status()

        # Extract archive into destination
        with tarfile.open(fileobj=io.BytesIO(resp.content)) as tar:
            tar.extractall(target)

    # Retry several times the download process
    cli_common.utils.retry(_download)
