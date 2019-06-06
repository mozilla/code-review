# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import copy
import datetime
import hashlib
import os
import re

import requests
import structlog
import taskcluster
import toml

logger = structlog.get_logger(__name__)

TASKCLUSTER_DATE_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'

with open(taskcluster._client_importer.__file__) as f:
    TASKCLUSTER_SERVICES = [
        line.split(' ')[1][1:]
        for line in f.read().split('\n')
        if line
    ]


def read_hosts():
    '''
    Read /etc/hosts to get hostnames
    on a Nix env (used for taskclusterProxy)
    Only reads ipv4 entries to avoid duplicates
    '''
    out = {}
    regex = re.compile(r'([\w:\-\.]+)')
    for line in open('/etc/hosts').readlines():
        if ':' in line:  # only ipv4
            continue
        x = regex.findall(line)
        if not x:
            continue
        ip, names = x[0], x[1:]
        out.update(dict(zip(names, [ip] * len(names))))

    return out


class TaskclusterConfig(object):
    '''
    Local configuration used to access Taskcluster service and objects
    '''
    def __init__(self):
        self.options = None
        self.secrets = None

    def auth(self, client_id=None, access_token=None):
        '''
        Build Taskcluster credentials options
        Supports, by order of preference:
         * directly provided credentials
         * credentials from local configuration
         * credentials from environment variables
         * taskclusterProxy
        '''
        self.options = {
            'maxRetries': 12,
        }

        if client_id is None and access_token is None:
            # Credentials preference: Use local config from release-services
            xdg = os.path.expanduser(os.environ.get('XDG_CONFIG_HOME', '~/.config'))
            config = os.path.join(xdg, 'please', 'config.toml')
            try:
                assert os.path.exists(config), 'No user config available'
                data = toml.load(open(config))
                client_id = data['common']['taskcluster_client_id']
                access_token = data['common']['taskcluster_access_token']
                assert client_id is not None and access_token is not None, \
                    'Missing values in user folder'
                logger.info('Using taskcluster credentials from local configuration')
            except Exception:
                # Credentials preference: Use env. variables
                client_id = os.environ.get('TASKCLUSTER_CLIENT_ID')
                access_token = os.environ.get('TASKCLUSTER_ACCESS_TOKEN')
                logger.info('Using taskcluster credentials from environment')
        else:
            logger.info('Using taskcluster credentials from cli')

        if client_id is not None and access_token is not None:
            # Use provided credentials
            self.options['credentials'] = {
                'clientId': client_id,
                'accessToken': access_token,
            }
            self.options['rootUrl'] = 'https://taskcluster.net'

        else:
            # Get taskcluster proxy host
            # as /etc/hosts is not used in the Nix image (?)
            hosts = read_hosts()
            if 'taskcluster' not in hosts:
                raise Exception('Missing taskcluster in /etc/hosts')

            # Load secrets from TC task context
            # with taskclusterProxy
            root_url = f"http://{hosts['taskcluster']}"

            logger.info('Taskcluster Proxy enabled', url=root_url)
            self.options['rootUrl'] = root_url

    def get_service(self, service_name):
        '''
        Build a Taskcluster service instance using current authentication
        '''
        assert self.options is not None, 'Not authenticated'
        assert service_name in TASKCLUSTER_SERVICES, \
            f'Service `{service_name}` does not exists.'

        return getattr(taskcluster, service_name.capitalize())(self.options)

    def load_secrets(self, name, project_name, required=[], existing=dict()):
        '''
        Fetch a specific set of secrets by name and verify that the required
        secrets exist.

        Merge secrets in the following order (the latter overrides the former):
            - `existing` argument
            - common secrets, specified under the `common` key in the secrets
              object
            - project specific secrets, specified under the `project_name` key in
              the secrets object
        '''
        assert name is not None, 'Missing Taskcluster secret name'
        self.secrets = dict()
        if existing:
            self.secrets = copy.deepcopy(existing)

        secrets_service = self.get_service('secrets')
        all_secrets = secrets_service.get(name).get('secret', dict())
        logger.info('Loaded Taskcluster secret', name=name)

        secrets_common = all_secrets.get('common', dict())
        self.secrets.update(secrets_common)

        secrets_app = all_secrets.get(project_name, dict())
        self.secrets.update(secrets_app)

        for required_secret in required:
            if required_secret not in self.secrets:
                raise Exception(f'Missing value {required_secret} in secrets.')


def create_blob_artifact(queue_service, task_id, run_id, path, content, content_type, ttl):
    '''
    Manually create and upload a blob artifact to use a specific content type
    '''
    assert isinstance(content, str)
    assert isinstance(ttl, datetime.timedelta)

    # Create artifact on Taskcluster
    sha256 = hashlib.sha256(content.encode('utf-8')).hexdigest()
    resp = queue_service.createArtifact(
        task_id,
        run_id,
        path,
        {
            'storageType': 'blob',
            'expires': (datetime.datetime.utcnow() + ttl).strftime(TASKCLUSTER_DATE_FORMAT),
            'contentType': content_type,
            'contentSha256': sha256,
            'contentLength': len(content),
        }
    )
    assert resp['storageType'] == 'blob', 'Not a blob storage'
    assert len(resp['requests']) == 1, 'Should only get one request'
    request = resp['requests'][0]
    assert request['method'] == 'PUT', 'Should get a PUT request'

    # Push the artifact on storage service
    push = requests.put(
        url=request['url'],
        headers=request['headers'],
        data=content,
    )
    push.raise_for_status()

    # Mark artifact as completed
    queue_service.completeArtifact(
        task_id,
        run_id,
        path,
        {
            'etags': [
                push.headers['ETag'],
            ],
        }
    )

    # Build the absolute url
    return f'https://queue.taskcluster.net/v1/task/{task_id}/runs/{run_id}/artifacts/{path}'
