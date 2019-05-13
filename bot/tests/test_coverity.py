# -*- coding: utf-8 -*-
import json
import os

from conftest import MOCK_DIR
from static_analysis_bot.tasks.coverity import CoverityIssue
from static_analysis_bot.tasks.coverity import CoverityTask
from static_analysis_bot.tasks.coverity import Reliability


class MockCoverityTask(CoverityTask):
    def __init__(self):
        '''
        Simply skip task loading
        '''


def mock_coverity(name):
    '''
    Load a Coverity mock file, as a Taskcluster artifact payload
    '''
    path = os.path.join(MOCK_DIR, 'coverity_{}.json'.format(name))
    assert os.path.exists(path), 'Missing coverity mock {}'.format(path)
    with open(path) as f:
        return {
            'public/code-review/coverity.json': json.load(f),
        }


def test_simple(mock_revision, mock_config):
    '''
    Test parsing a simple Coverity artifact
    '''
    assert mock_config.cov_full_stack is False
    mock_config.cov_full_stack = True

    task = MockCoverityTask()
    issues = task.parse_issues(mock_coverity('simple'), mock_revision)
    assert len(issues) == 1
    assert all(map(lambda i: isinstance(i, CoverityIssue), issues))

    # Revert value to avoid side effects on other tests
    mock_config.cov_full_stack = False

    issue = issues[0]

    assert issue.revision == mock_revision
    assert issue.reliability == Reliability.Medium
    assert issue.path == 'js/src/jit/BaselineCompiler.cpp'
    assert issue.line == 3703
    assert issue.bug_type == 'Null pointer dereferences'
    assert issue.kind == 'NULL_RETURNS'
    assert issue.message == '''Dereferencing a pointer that might be "nullptr" "env" when calling "lookupImport".
The path that leads to this defect is:

- ///builds/worker/checkouts/gecko/js/src/jit/BaselineCompiler.cpp:3697//:
-- `returned_null: "GetModuleEnvironmentForScript" returns "nullptr" (checked 2 out of 2 times).`.

- ///builds/worker/checkouts/gecko/js/src/jit/BaselineCompiler.cpp:3697//:
-- `var_assigned: Assigning: "env" = "nullptr" return value from "GetModuleEnvironmentForScript".`.

- ///builds/worker/checkouts/gecko/js/src/jit/BaselineCompiler.cpp:3703//:
-- `dereference: Dereferencing a pointer that might be "nullptr" "env" when calling "lookupImport".`.
'''
    assert issue.state_on_server == {
        'cached': False,
        'cid': 95687,
        'components': ['js'],
        'customTriage': {},
        'firstDetectedDateTime': '2019-04-08T12:57:07+00:00',
        'ownerLdapServerName': 'local',
        'presentInReferenceSnapshot': False,
        'retrievalDateTime': '2019-05-13T10:20:22+00:00',
        'stream': 'Firefox',
        'triage': {
            'action': 'Undecided',
            'classification': 'Unclassified',
            'externalReference': '',
            'fixTarget': 'Untargeted',
            'legacy': 'False',
            'owner': 'try',
            'severity': 'Unspecified',
        }
    }
    assert issue.body is None
    assert issue.nb_lines == 1

    assert issue.validates()
    assert issue.is_publishable()

    assert issue.as_text() == '''Checker reliability (false positive risk) is medium.
Dereferencing a pointer that might be "nullptr" "env" when calling "lookupImport".
The path that leads to this defect is:

- ///builds/worker/checkouts/gecko/js/src/jit/BaselineCompiler.cpp:3697//:
-- `returned_null: "GetModuleEnvironmentForScript" returns "nullptr" (checked 2 out of 2 times).`.

- ///builds/worker/checkouts/gecko/js/src/jit/BaselineCompiler.cpp:3697//:
-- `var_assigned: Assigning: "env" = "nullptr" return value from "GetModuleEnvironmentForScript".`.

- ///builds/worker/checkouts/gecko/js/src/jit/BaselineCompiler.cpp:3703//:
-- `dereference: Dereferencing a pointer that might be "nullptr" "env" when calling "lookupImport".`.
'''
    assert issue.as_dict() == {
        'analyzer': 'Coverity',
        'body': None,
        'bug_type': 'Null pointer dereferences',
        'in_patch': False,
        'is_local': True,
        'is_new': False,
        'kind': 'NULL_RETURNS',
        'line': 3703,
        'message': '''Dereferencing a pointer that might be "nullptr" "env" when calling "lookupImport".
The path that leads to this defect is:

- ///builds/worker/checkouts/gecko/js/src/jit/BaselineCompiler.cpp:3697//:
-- `returned_null: "GetModuleEnvironmentForScript" returns "nullptr" (checked 2 out of 2 times).`.

- ///builds/worker/checkouts/gecko/js/src/jit/BaselineCompiler.cpp:3697//:
-- `var_assigned: Assigning: "env" = "nullptr" return value from "GetModuleEnvironmentForScript".`.

- ///builds/worker/checkouts/gecko/js/src/jit/BaselineCompiler.cpp:3703//:
-- `dereference: Dereferencing a pointer that might be "nullptr" "env" when calling "lookupImport".`.
''',
        'nb_lines': 1,
        'path': 'js/src/jit/BaselineCompiler.cpp',
        'publishable': True,
        'reliability': 'medium',
        'validates': True,
        'validation': {
            'is_clang_error': False,
            'is_local': True,
        }
    }
