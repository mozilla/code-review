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
import taskcluster

from cli_common.log import get_logger
from static_analysis_bot.config import settings
from static_analysis_bot import AnalysisException


logger = get_logger(__name__)

ANDROID_MOZCONFIG = '''# Build Firefox for Android:
ac_add_options --enable-application=mobile/android
ac_add_options --target=arm-linux-androideabi

# With the following Android SDK and NDK:
ac_add_options --with-android-sdk="{mozbuild}/android-sdk-linux/android-sdk-linux"
ac_add_options --with-android-ndk="{mozbuild}/android-ndk/android-ndk"'''

GRADLE_PROPERTIES = '''
// Per https://docs.gradle.org/current/userguide/build_environment.html, this
// overrides the gradle.properties in topsrcdir.
org.gradle.daemon=false
'''


def setup(index, job_name='linux64-infer', revision='latest',
          artifact='public/build/infer.tar.xz'):
    '''
    Setup Taskcluster infer build for static-analysis
    Defaults values are from https://dxr.mozilla.org/mozilla-central/source/taskcluster/ci/toolchain/linux.yml
    - Download the artifact from latest Taskcluster build
    - Extracts it into the MOZBUILD_STATE_PATH as expected by mach
    '''
    if job_name == 'linux64-infer':
        jobs = [
            {
                'job-name': 'linux64-infer',
                'artifact': 'public/build/infer.tar.xz',
                'namespace': 'gecko.v2.autoland.latest.static-analysis.linux64-infer'
            },
            {
                'job-name': 'linux64-android-sdk-linux-repack',
                'artifact': 'project/gecko/android-sdk/android-sdk-linux.tar.xz',
                'namespace': 'gecko.cache.level-1.toolchains.v2.linux64-android-sdk-linux-repack.latest'
            },
            {
                'job-name': 'linux64-android-ndk-linux-repack',
                'artifact': 'project/gecko/android-ndk/android-ndk.tar.xz',
                'namespace': 'gecko.cache.level-1.toolchains.v2.linux64-android-ndk-linux-repack.latest'
            }
        ]

        for element in jobs:
            namespace = element['namespace']
            artifact = element['artifact']
            # on staging buildSignedUrl will fail, because the artifacts are downloaded from
            # a proxy, therefore we need to use buildUrl in case the signed version fails
            try:
                artifact_url = index.buildSignedUrl('findArtifactFromTask',
                                                    indexPath=namespace,
                                                    name=artifact,
                                                    expiration=7200)
            except taskcluster.exceptions.TaskclusterAuthFailure:
                artifact_url = index.buildUrl('findArtifactFromTask',
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
                mozbuild=os.environ['MOZBUILD_STATE_PATH']))

        # set GRADLE_USER_HOME as it is needed for Gradle to use sane paths.
        gradle_home_dir = os.path.join(
            os.environ['MOZBUILD_STATE_PATH'], 'gradle')
        if not os.path.exists(gradle_home_dir):
            os.makedirs(gradle_home_dir)
        logger.info('Setting GRADLE_USER_HOME to {}.'.format(gradle_home_dir))
        os.environ['GRADLE_USER_HOME'] = gradle_home_dir

        # Create the gradle.properties file and add the necessary flags
        with open(os.path.join(gradle_home_dir, 'gradle.properties'), 'a') as f:
            f.write(GRADLE_PROPERTIES)

    def __exit__(self, type, value, traceback):
        os.environ['MOZCONFIG'] = self.__old_config
        os.remove(self.__android_mozconfig)
