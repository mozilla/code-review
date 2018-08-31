# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import itertools
import json
import os.path
import re
import subprocess
import tempfile
import time
from contextlib import contextmanager
from distutils.spawn import find_executable
from unittest.mock import Mock

import hglib
import httpretty
import pytest
import responses

from cli_common.phabricator import PhabricatorAPI

MOCK_DIR = os.path.join(os.path.dirname(__file__), 'mocks')

TEST_CPP = '''include <cstdio>

int main(void){
    printf("Hello world!");
    return 0;
}
'''


@responses.activate
@pytest.fixture(scope='session')
def mock_config():
    '''
    Mock configuration for bot
    '''
    path = os.path.join(MOCK_DIR, 'config.yaml')
    responses.add(
        responses.GET,
        'https://hg.mozilla.org/mozilla-central/raw-file/tip/tools/clang-tidy/config.yaml',
        body=open(path).read(),
        content_type='text/plain',
    )

    from static_analysis_bot.config import settings
    tempdir = tempfile.mkdtemp()
    settings.setup('test', tempdir, 'IN_PATCH')

    return settings


@pytest.fixture(scope='session')
def mock_repository(mock_config):
    '''
    Create a dummy mercurial repository
    '''
    # Init repo
    hglib.init(mock_config.repo_dir)

    # Init clean client
    client = hglib.open(mock_config.repo_dir)

    # Add test.txt file
    path = os.path.join(mock_config.repo_dir, 'test.txt')
    with open(path, 'w') as f:
        f.write('Hello World\n')

    # Initiall commit
    client.add(path.encode('utf-8'))
    client.commit(b'Hello World', user=b'Tester')

    # Write dummy 3rd party file
    third_party = os.path.join(mock_config.repo_dir, mock_config.third_party)
    with open(third_party, 'w') as f:
        f.write('test/dummy')

    # Remove pull capabilities
    client.pull = Mock(return_value=True)

    return client


@pytest.fixture
def mock_issues():
    '''
    Build a list of dummy issues
    '''

    class MockIssue(object):
        def __init__(self, nb):
            self.nb = nb

        def as_markdown(self):
            return str(self.nb)

        def as_text(self):
            return str(self.nb)

        def as_dict(self):
            return {
                'nb': self.nb,
            }

        def is_publishable(self):
            return self.nb % 2 == 0

    return [
        MockIssue(i)
        for i in range(5)
    ]


@pytest.fixture
def mock_mozreview():
    '''
    Mock mozreview authentication process
    Need to use httpretty as mozreview uses low level urlopen
    '''
    api_url = 'http://mozreview.test/api/'
    auth_url = api_url + 'extensions/mozreview.extension.MozReviewExtension/bugzilla-api-key-logins/'
    session_url = api_url + 'session/'

    def _response(name, extension='json'):
        path = os.path.join(MOCK_DIR, 'mozreview_{}.{}'.format(name, extension))
        assert os.path.exists(path)
        return open(path).read()

    # Start httpretty session
    httpretty.enable()

    # API Root endpoint
    httpretty.register_uri(
        httpretty.GET,
        api_url,
        body=_response('root'),
        content_type='application/vnd.reviewboard.org.root+json',
    )

    # Initial query to get auth endpoints
    httpretty.register_uri(
        httpretty.GET,
        auth_url,
        body=_response('auth'),
        content_type='application/vnd.reviewboard.org.bugzilla-api-key-logins+json',
    )

    # Current session query
    httpretty.register_uri(
        httpretty.GET,
        session_url,
        body=_response('session'),
        content_type='application/vnd.reviewboard.org.session+json',
    )

    # User details queries
    httpretty.register_uri(
        httpretty.GET,
        api_url + 'users/devbot/',
        body=_response('user'),
        content_type='application/vnd.reviewboard.org.user+json',
    )
    httpretty.register_uri(
        httpretty.GET,
        api_url + 'users/anotherUser/',
        body=_response('user_another'),
        content_type='application/vnd.reviewboard.org.user+json',
    )

    # Dummy Reviews list
    httpretty.register_uri(
        httpretty.GET,
        api_url + 'review-requests/12345/reviews/',
        body=_response('reviews_12345'),
        content_type='application/vnd.reviewboard.org.review+json',
    )

    # Dummy Review comment list
    httpretty.register_uri(
        httpretty.GET,
        api_url + 'review-requests/12345/reviews/51/diff-comments/',
        body=_response('comments_12345_51'),
        content_type='application/vnd.reviewboard.org.review-diff-comments+json',
    )

    # Dummy Review file diff
    httpretty.register_uri(
        httpretty.GET,
        api_url + 'review-requests/12345/diffs/2/files/',
        body=_response('files_12345'),
        content_type='application/vnd.reviewboard.org.files+json',
        adding_headers={
            'Item-Content-Type': 'application/vnd.reviewboard.org.file+json',
        }
    )

    def _filediff(request, uri, headers):

        if request.headers.get('Accept') == 'application/vnd.reviewboard.org.diff.data+json':
            # Diff data
            body = _response('filediff_12345_2_diffdata')
            headers['content-type'] = 'application/vnd.reviewboard.org.diff.data+json'

        else:

            # Basic data
            body = _response('filediff_12345_2')
            headers['content-type'] = 'application/vnd.reviewboard.org.file+json'

        return (200, headers, body)

    httpretty.register_uri(
        httpretty.GET,
        api_url + 'review-requests/12345/diffs/2/files/31/',
        body=_filediff,
    )

    def _check_credentials(request, uri, headers):

        # Dirty multipart form data "parser"
        form = dict(re.findall(r'name="([\w_]+)"\r\n\r\n(\w+)\r\n', request.body.decode('utf-8')))
        assert form['username'] == 'devbot'
        assert form['api_key'] == 'deadbeef123'

        body = json.dumps({
            'stat': 'ok',
            'bugzilla_api_key_login': {
                'email': 'devbot@mozilla.org',
            },
        })
        return (201, headers, body)

    # Initial query to get auth endpoints
    httpretty.register_uri(
        httpretty.POST,
        auth_url,
        status_code=201,
        body=_check_credentials,
        content_type='application/vnd.reviewboard.org.bugzilla-api-key-logins+json',
    )

    # Pass context to test runtime
    yield

    # Close httpretty session
    httpretty.disable()


@contextmanager
@pytest.fixture
def mock_phabricator():
    '''
    Mock phabricator authentication process
    '''
    def _response(name):
        path = os.path.join(MOCK_DIR, 'phabricator_{}.json'.format(name))
        assert os.path.exists(path)
        return open(path).read()

    responses.add(
        responses.POST,
        'http://phabricator.test/api/user.whoami',
        body=_response('auth'),
        content_type='application/json',
    )

    responses.add(
        responses.POST,
        'http://phabricator.test/api/differential.diff.search',
        body=_response('diff_search'),
        content_type='application/json',
    )

    responses.add(
        responses.POST,
        'http://phabricator.test/api/differential.revision.search',
        body=_response('revision_search'),
        content_type='application/json',
    )

    responses.add(
        responses.POST,
        'http://phabricator.test/api/differential.query',
        body=_response('diff_query'),
        content_type='application/json',
    )

    responses.add(
        responses.POST,
        'http://phabricator.test/api/differential.getrawdiff',
        body=_response('diff_raw'),
        content_type='application/json',
    )

    responses.add(
        responses.POST,
        'http://phabricator.test/api/edge.search',
        body=_response('edge_search'),
        content_type='application/json',
    )

    yield PhabricatorAPI(
        url='http://phabricator.test/api/',
        api_key='deadbeef',
    )


@pytest.fixture(scope='session')
def mock_stats(mock_config):
    '''
    Mock Datadog authentication and stats management
    '''
    from static_analysis_bot import stats

    # Configure Datadog with a dummy token
    # and an ultra fast flushing cycle
    stats.auth('test_token')
    stats.api.stop()
    stats.api.start(flush_interval=0.001)
    assert not stats.api._disabled
    assert stats.api._is_auto_flushing

    class MemoryReporter(object):
        '''
        A reporting class that reports to memory for testing.
        Used in datadog unit tests:
        https://github.com/DataDog/datadogpy/blob/master/tests/unit/threadstats/test_threadstats.py
        '''
        def __init__(self, api):
            self.metrics = []
            self.events = []
            self.api = api

        def flush_metrics(self, metrics):
            self.metrics += metrics

        def flush_events(self, events):
            self.events += events

        def flush(self):
            # Helper for unit tests to force flush
            self.api.flush(time.time() + 20)

        def get_metrics(self, metric_name):
            return list(itertools.chain(*[
                [
                    [t, point * m['interval']]
                    for t, point in m['points']
                ]
                for m in self.metrics
                if m['metric'] == metric_name
            ]))

    # Gives reporter access to unit tests to access metrics
    stats.api.reporter = MemoryReporter(stats.api)
    yield stats.api.reporter


@pytest.fixture
def mock_revision():
    '''
    Mock a mercurial revision
    '''
    from static_analysis_bot.revisions import Revision
    rev = Revision()
    rev.mercurial = 'a6ce14f59749c3388ffae2459327a323b6179ef0'
    return rev


@pytest.fixture
def mock_clang(tmpdir, monkeypatch):
    '''
    Mock clang binary setup by linking the system wide
    clang tools into the expected repo sub directory
    '''

    # Create a temp mozbuild path
    clang_dir = tmpdir.mkdir('clang-tools').mkdir('clang').mkdir('bin')
    os.environ['MOZBUILD_STATE_PATH'] = str(tmpdir.realpath())

    for tool in ('clang-tidy', 'clang-format'):
        os.symlink(
            find_executable(tool),
            str(clang_dir.join(tool).realpath()),
        )

    # Monkeypatch the mach static analysis by using directly clang-tidy
    real_check_output = subprocess.check_output

    def mock_mach(command, *args, **kwargs):
        if command[:5] == ['gecko-env', './mach', '--log-no-times', 'static-analysis', 'check']:
            command = ['clang-tidy', ] + command[5:]
            output = real_check_output(command, *args, **kwargs)
            return output + b'\n42 warnings present.'

        # Really run command through normal check_output
        return real_check_output(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, 'check_output', mock_mach)


@responses.activate
@pytest.fixture
def mock_workflow(tmpdir, mock_repository, mock_config, mock_phabricator):
    '''
    Mock the full workflow, without cloning
    '''
    from static_analysis_bot.workflow import Workflow

    class MockWorkflow(Workflow):
        def clone(self):
            return hglib.open(mock_config.repo_dir)

    # Needed for Taskcluster build
    if 'MOZCONFIG' not in os.environ:
        os.environ['MOZCONFIG'] = str(tmpdir.join('mozconfig').realpath())

    with mock_phabricator as api:
        workflow = MockWorkflow(
            reporters={},
            analyzers=['clang-tidy', 'clang-format', 'mozlint'],
            index_service=None,
            phabricator_api=api,
        )
    workflow.hg = workflow.clone()
    return workflow


@pytest.fixture
def test_cpp(mock_config, mock_repository):
    '''
    Build a dummy test.cpp file in repo
    '''
    path = os.path.join(mock_config.repo_dir, 'test.cpp')
    with open(path, 'w') as f:
        f.write(TEST_CPP)


@pytest.fixture
def mock_clang_output():
    '''
    Load a real case clang output
    '''
    path = os.path.join(MOCK_DIR, 'clang-output.txt')
    with open(path) as f:
        return f.read()


@pytest.fixture
def mock_clang_issues():
    '''
    Load parsed issues from a real case (above)
    '''
    path = os.path.join(MOCK_DIR, 'clang-issues.txt')
    with open(path) as f:
        return f.read()


@pytest.fixture
def mock_clang_repeats(mock_config):
    '''
    Load parsed issues with repeated issues
    '''
    # Write dummy test_repeat.cpp file in repo
    # Needed to build line hash
    test_cpp = os.path.join(mock_config.repo_dir, 'test_repeats.cpp')
    with open(test_cpp, 'w') as f:
        for i in range(5):
            f.write('line {}\n'.format(i))

    path = os.path.join(MOCK_DIR, 'clang-repeats.txt')
    with open(path) as f:
        return f.read().replace('{REPO}', mock_config.repo_dir)
