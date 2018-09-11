# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import tarfile
import requests
import io
import os
import shutil
import subprocess
import cli_common.utils

from cli_common.log import get_logger
from static_analysis_bot.config import settings
from static_analysis_bot import AnalysisException


logger = get_logger(__name__)

ANDROID_MOZCONFIG = '''# Build Firefox for Android:
ac_add_options --enable-application=mobile/android
ac_add_options --target=arm-linux-androideabi

# With the following Android SDK and NDK:
ac_add_options --with-android-sdk="{mozbuild}/android-sdk-linux/android-sdk-linux"
ac_add_options --with-android-ndk="{mozbuild}/android-ndk/android-ndk"

ac_add_options --with-java-bin-path="{openjdk}/bin"
'''


def setup(index, job_name='linux64-infer', revision='latest',
          artifact='public/build/infer.tar.xz'):
    '''
    Setup Taskcluster infer build for static-analysis
    Defaults values are from https://dxr.mozilla.org/mozilla-central/source/taskcluster/ci/toolchain/linux.yml
    - Download the artifact from latest Taskcluster build
    - Extracts it into the MOZBUILD_STATE_PATH as expected by mach
    '''
    NAMESPACE = 'gecko.cache.level-1.toolchains.v2.{}.{}'
    if job_name == 'linux64-infer':
        job_names = ['linux64-infer', 'linux64-android-sdk-linux-repack',
                     'linux64-android-ndk-linux-repack']
        artifacts = ['public/build/infer.tar.xz',
                     'project/gecko/android-sdk/android-sdk-linux.tar.xz',
                     'project/gecko/android-ndk/android-ndk.tar.xz']
        for job, artifact in zip(job_names, artifacts):
            namespace = NAMESPACE.format(job, revision)
            artifact_url = index.buildSignedUrl('findArtifactFromTask',
                                                indexPath=namespace,
                                                name=artifact)
            target = os.path.join(
                os.environ['MOZBUILD_STATE_PATH'],
                os.path.basename(artifact).split('.')[0],
            )
            logger.info('Downloading {}.'.format(artifact))
            cli_common.utils.retry(lambda: download(artifact_url, target))
            if not os.path.exists(target):
                raise AnalysisException('artifact', 'Setup failed for {}'.format(target))


def download(artifact_url, target):
    # Download Taskcluster archive
    resp = requests.get(artifact_url, stream=True)
    resp.raise_for_status()

    # Extract archive into destination
    with tarfile.open(fileobj=io.BytesIO(resp.content)) as tar:
        tar.extractall(target)


class AndroidConfig():
    def __enter__(self):
        # we copy the old mozconfig into the repository, so that we can
        # enable the android build
        self.__android_mozconfig = os.path.join(settings.repo_dir, 'mozconfig')
        self.__old_config = os.getenv('MOZCONFIG')
        shutil.copy(self.__old_config, self.__android_mozconfig)
        os.environ['MOZCONFIG'] = self.__android_mozconfig
        subprocess.run(['chmod', 'u+w', self.__android_mozconfig])
        with open(self.__android_mozconfig, 'a') as f:
            f.write(ANDROID_MOZCONFIG.format(
                mozbuild='/tmp/mozilla-state',
                openjdk=os.getenv('JAVA_HOME')))

    def __exit__(self, type, value, traceback):
        os.environ['MOZCONFIG'] = self.__old_config
        os.remove(self.__android_mozconfig)
