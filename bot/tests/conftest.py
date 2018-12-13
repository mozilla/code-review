# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import itertools
import os.path
import subprocess
import tempfile
import time
from contextlib import contextmanager
from distutils.spawn import find_executable
from unittest.mock import Mock

import hglib
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


@pytest.fixture(scope='session')
@responses.activate
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
    settings.setup('test', tempdir, 'IN_PATCH', ['dom/*', 'tests/*.py', 'test/*.c'])

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
            return 'This is the mock issue n°{}'.format(self.nb)

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
@responses.activate
@contextmanager
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
        'http://phabricator.test/api/differential.createinline',
        body=_response('createinline'),
        content_type='application/json',
    )

    responses.add(
        responses.POST,
        'http://phabricator.test/api/edge.search',
        body=_response('edge_search'),
        content_type='application/json',
    )

    responses.add(
        responses.POST,
        'http://phabricator.test/api/transaction.search',
        body=_response('transaction_search'),
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
def mock_clang(mock_config, tmpdir, monkeypatch):
    '''
    Mock clang binary setup by linking the system wide
    clang tools into the expected repo sub directory
    '''

    # Create a temp mozbuild path
    clang_dir = tmpdir.mkdir('clang-tools').mkdir('clang-tidy').mkdir('bin')
    os.environ['MOZBUILD_STATE_PATH'] = str(tmpdir.realpath())

    for tool in ('clang-tidy', 'clang-format'):
        os.symlink(
            find_executable(tool),
            str(clang_dir.join(tool).realpath()),
        )

    # Monkeypatch the mach static analysis by using directly clang-tidy
    real_run = subprocess.run

    def mock_mach(command, *args, **kwargs):
        if command[:5] == ['gecko-env', './mach', '--log-no-times', 'static-analysis', 'check']:
            command = ['clang-tidy', ] + command[5:]
            res = real_run(command, *args, **kwargs)
            res.stdout = res.stdout + b'\n42 warnings present.'
            return res

        if command[:5] == ['gecko-env', './mach', '--log-no-times', 'clang-format']:
            # Mock ./mach clang-format behaviour by analysing repo bad file
            # with the embedded clang-format from Nix
            # and replace this file with the output
            target = os.path.join(mock_config.repo_dir, 'dom', 'bad.cpp')
            out = real_run(['clang-format', target], *args, **kwargs)
            with open(target, 'w') as f:
                f.write(out.stdout.decode('utf-8'))

            # Must return command output as it's saved as TC artifact
            return out

        # Really run command through normal run
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, 'run', mock_mach)


@pytest.fixture
@responses.activate
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
            queue_service=None,
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


@pytest.fixture
def mock_infer(tmpdir, monkeypatch):
    # Create a temp mozbuild path
    infer_dir = tmpdir.mkdir('infer').mkdir('infer').mkdir('bin')
    os.environ['MOZBUILD_STATE_PATH'] = str(tmpdir.realpath())

    open(str(infer_dir.join('infer').realpath()), 'w+')


@pytest.fixture
def mock_infer_output():
    '''
    Load a real case clang output
    '''
    path = os.path.join(MOCK_DIR, 'infer-output.txt')
    with open(path) as f:
        return f.read()


@pytest.fixture
def mock_infer_issues():
    '''
    Load parsed issues from a real case (above)
    '''
    path = os.path.join(MOCK_DIR, 'infer-issues.txt')
    with open(path) as f:
        return f.read()


@pytest.fixture
def mock_infer_repeats(mock_config):
    '''
    Load parsed issues with repeated issues
    '''
    # Write dummy test_repeat.cpp file in repo
    # Needed to build line hash
    test_java = os.path.join(mock_config.repo_dir, 'test_repeats.java')
    with open(test_java, 'w') as f:
        for i in range(5):
            f.write('line {}\n'.format(i))

    path = os.path.join(MOCK_DIR, 'infer-repeats.txt')
    with open(path) as f:
        return f.read().replace('{REPO}', mock_config.repo_dir)
