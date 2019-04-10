# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from collections import namedtuple

import pytest

MockArtifactResponse = namedtuple('MockArtifactResponse', 'content')


class MockQueue(object):
    '''
    Mock the Taskcluster queue, by using fake tasks descriptions, relations and artifacts
    '''

    def __init__(self, relations):
        # Create tasks
        assert isinstance(relations, dict)
        self._tasks = {
            task_id: {
                'dependencies': desc.get('dependencies', []),
                'metadata': {
                    'name': desc.get('name', 'source-test-mozlint-{}'.format(task_id)),
                },
                'payload': {
                    'image': desc.get('image', 'alpine'),
                    'env': desc.get('env', {}),
                }
            }
            for task_id, desc in relations.items()
        }

        # Create status
        self._status = {
            task_id: {
                'status': {
                    'taskId': task_id,
                    'state': desc.get('state', 'completed'),
                    'runs': [
                        {
                            'runId': 0,
                        }
                    ]
                }
            }
            for task_id, desc in relations.items()
        }

        # Create artifacts
        self._artifacts = {
            task_id: {
                'artifacts': [
                    {
                        'name': name,
                        'storageType': 'dummyStorage',
                        'contentType': isinstance(artifact, (dict, list)) and 'application/json' or 'text/plain',
                        'content': artifact,
                    }
                    for name, artifact in desc.get('artifacts', {}).items()
                ]
            }
            for task_id, desc in relations.items()
        }

    def task(self, task_id):
        return self._tasks[task_id]

    def status(self, task_id):
        return self._status[task_id]

    def listTaskGroup(self, group_id):
        return {
            'tasks': [
                {
                    'task': self.task(task_id),
                    'status': self.status(task_id)['status'],
                }
                for task_id in self._tasks.keys()
            ]
        }

    def listArtifacts(self, task_id, run_id):
        return self._artifacts.get(task_id, {})

    def getArtifact(self, task_id, run_id, artifact_name):
        artifacts = self._artifacts.get(task_id, {})
        if not artifacts:
            return

        artifact = next(filter(lambda a: a['name'] == artifact_name, artifacts['artifacts']))
        if artifact['contentType'] == 'application/json':
            return artifact['content']
        return {
            'response': MockArtifactResponse(artifact['content'].encode('utf-8')),
        }


def test_no_deps(mock_try_config, mock_revision):
    '''
    Test an error occurs when no dependencies are found on root task
    '''
    from static_analysis_bot.workflows.remote import RemoteWorkflow

    tasks = {
        'decision': {
            'image': 'taskcluster/decision:XXX',
            'env': {
                'GECKO_HEAD_REPOSITORY': 'https://hg.mozilla.org/try',
                'GECKO_HEAD_REV': 'deadbeef1234',
            }
        },
        'remoteTryTask': {},
        'extra-task': {},
    }
    workflow = RemoteWorkflow(MockQueue(tasks))
    with pytest.raises(AssertionError) as e:
        workflow.run(mock_revision)
    assert str(e.value) == 'No task dependencies to analyze'


def test_baseline(mock_try_config, mock_revision):
    '''
    Test a normal remote workflow (aka Try mode)
    - current task with analyzer deps
    - an analyzer in failed status
    - with some issues in its log
    '''
    from static_analysis_bot.workflows.remote import RemoteWorkflow
    from static_analysis_bot.lint import MozLintIssue

    # We run on a mock TC, with a try source
    assert mock_try_config.taskcluster.task_id == 'local instance'
    assert mock_try_config.source == 'try'
    assert mock_try_config.try_task_id == 'remoteTryTask'

    # We do not want to check local files with this worfklow
    mock_try_config.has_local_clone = False

    tasks = {
        'decision': {
            'image': 'taskcluster/decision:XXX',
            'env': {
                'GECKO_HEAD_REPOSITORY': 'https://hg.mozilla.org/try',
                'GECKO_HEAD_REV': 'deadbeef1234',
            }
        },
        'remoteTryTask': {
            'dependencies': ['analyzer-A', 'analyzer-B']
        },
        'analyzer-A': {
            'name': 'source-test-mozlint-flake8',
            'state': 'failed',
            'artifacts': {
                'public/code-review/mozlint.json': {
                    'test.cpp': [
                        {
                            'path': 'test.cpp',
                            'lineno': 12,
                            'column': 1,
                            'level': 'error',
                            'linter': 'flake8',
                            'rule': 'checker XXX',
                            'message': 'strange issue',
                        }
                    ]
                },
            }
        },
        'analyzer-B': {},
        'extra-task': {},
    }
    workflow = RemoteWorkflow(MockQueue(tasks))
    issues = workflow.run(mock_revision)

    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, MozLintIssue)
    assert issue.path == 'test.cpp'
    assert issue.line == 12
    assert issue.column == 1
    assert issue.message == 'strange issue'
    assert issue.rule == 'checker XXX'
    assert issue.revision is mock_revision
    assert issue.validates()


def test_no_failed(mock_try_config, mock_revision):
    '''
    Test a remote workflow without any failed tasks
    '''
    from static_analysis_bot.workflows.remote import RemoteWorkflow

    tasks = {
        'decision': {
            'image': 'taskcluster/decision:XXX',
            'env': {
                'GECKO_HEAD_REPOSITORY': 'https://hg.mozilla.org/try',
                'GECKO_HEAD_REV': 'deadbeef1234',
            }
        },
        'remoteTryTask': {
            'dependencies': ['analyzer-A', 'analyzer-B']
        },
        'analyzer-A': {},
        'analyzer-B': {},
        'extra-task': {},
    }
    workflow = RemoteWorkflow(MockQueue(tasks))
    issues = workflow.run(mock_revision)
    assert len(issues) == 0


def test_no_issues(mock_try_config, mock_revision):
    '''
    Test a remote workflow without any issues in its artifacts
    '''
    from static_analysis_bot.workflows.remote import RemoteWorkflow

    tasks = {
        'decision': {
            'image': 'taskcluster/decision:XXX',
            'env': {
                'GECKO_HEAD_REPOSITORY': 'https://hg.mozilla.org/try',
                'GECKO_HEAD_REV': 'deadbeef1234',
            }
        },
        'remoteTryTask': {
            'dependencies': ['analyzer-A', 'analyzer-B']
        },
        'analyzer-A': {},
        'analyzer-B': {
            'name': 'source-test-mozlint-flake8',
            'state': 'failed',
            'artifacts': {
                'nope.log': 'No issues here !',
                'still-nope.txt': 'xxxxx',
                'public/code-review/mozlint.json': {},
            }
        },
        'extra-task': {},
    }
    workflow = RemoteWorkflow(MockQueue(tasks))
    issues = workflow.run(mock_revision)
    assert len(issues) == 0


def test_unsupported_analyzer(mock_try_config, mock_revision):
    '''
    Test a remote workflow with an unsupported analyzer (not mozlint)
    '''
    from static_analysis_bot.workflows.remote import RemoteWorkflow

    tasks = {
        'decision': {
            'image': 'taskcluster/decision:XXX',
            'env': {
                'GECKO_HEAD_REPOSITORY': 'https://hg.mozilla.org/try',
                'GECKO_HEAD_REV': 'deadbeef1234',
            }
        },
        'remoteTryTask': {
            'dependencies': ['analyzer-A', 'analyzer-B']
        },
        'analyzer-A': {},
        'analyzer-B': {
            'name': 'custom-analyzer-from-vendor',
            'state': 'failed',
            'artifacts': {
                'issue.log': 'TEST-UNEXPECTED-ERROR | test.cpp:12:1 | clearly an issue (checker XXX)',
            }
        },
        'extra-task': {},
    }
    workflow = RemoteWorkflow(MockQueue(tasks))
    with pytest.raises(Exception) as e:
        workflow.run(mock_revision)
    assert str(e.value) == 'Unsupported task custom-analyzer-from-vendor'


def test_decision_task(mock_try_config, mock_revision):
    '''
    Test a remote workflow with different decision task setup
    '''
    from static_analysis_bot.workflows.remote import RemoteWorkflow

    tasks = {
        'decision': {
        },
        'remoteTryTask': {
        },
    }
    workflow = RemoteWorkflow(MockQueue(tasks))
    with pytest.raises(AssertionError) as e:
        workflow.run(mock_revision)
    assert str(e.value) == 'Missing decision task'

    tasks = {
        'decision': {
            'image': 'anotherImage',
        },
        'remoteTryTask': {
        },
    }
    workflow = RemoteWorkflow(MockQueue(tasks))
    with pytest.raises(AssertionError) as e:
        workflow.run(mock_revision)
    assert str(e.value) == 'Missing decision task'

    tasks = {
        'decision': {
            'image': {
                'from': 'taskcluster/decision',
                'tag': 'unsupported',
            }
        },
        'remoteTryTask': {
        },
    }
    workflow = RemoteWorkflow(MockQueue(tasks))
    with pytest.raises(AssertionError) as e:
        workflow.run(mock_revision)
    assert str(e.value) == 'Missing decision task'

    tasks = {
        'decision': {
            'image': 'taskcluster/decision:XXX',
        },
        'remoteTryTask': {
        },
    }
    workflow = RemoteWorkflow(MockQueue(tasks))
    with pytest.raises(AssertionError) as e:
        workflow.run(mock_revision)
    assert str(e.value) == 'Not the try repo in GECKO_HEAD_REPOSITORY'

    tasks = {
        'decision': {
            'image': 'taskcluster/decision:XXX',
            'env': {
                'GECKO_HEAD_REPOSITORY': 'https://hg.mozilla.org/try',
            }
        },
        'remoteTryTask': {
        },
    }
    workflow = RemoteWorkflow(MockQueue(tasks))
    with pytest.raises(AssertionError) as e:
        workflow.run(mock_revision)
    assert str(e.value) == 'Missing try revision'
    assert mock_revision.mercurial_revision is None

    tasks = {
        'decision': {
            'image': 'taskcluster/decision:XXX',
            'env': {
                'GECKO_HEAD_REPOSITORY': 'https://hg.mozilla.org/try',
                'GECKO_HEAD_REV': 'someRevision'
            }
        },
        'remoteTryTask': {
        },
    }
    workflow = RemoteWorkflow(MockQueue(tasks))
    with pytest.raises(AssertionError) as e:
        workflow.run(mock_revision)
    assert str(e.value) == 'No task dependencies to analyze'
    assert mock_revision.mercurial_revision is not None
    assert mock_revision.mercurial_revision == 'someRevision'


def test_mozlint_task(mock_try_config, mock_revision):
    '''
    Test a remote workflow with a mozlint analyzer
    '''
    from static_analysis_bot.workflows.remote import RemoteWorkflow
    from static_analysis_bot.lint import MozLintIssue

    tasks = {
        'decision': {
            'image': 'taskcluster/decision:XXX',
            'env': {
                'GECKO_HEAD_REPOSITORY': 'https://hg.mozilla.org/try',
                'GECKO_HEAD_REV': 'deadbeef1234',
            }
        },
        'remoteTryTask': {
            'dependencies': ['mozlint']
        },
        'mozlint': {
            'name': 'source-test-mozlint-dummy',
            'state': 'failed',
            'artifacts': {
                'public/code-review/mozlint.json': {
                    'test.cpp': [
                        {
                            'path': 'test.cpp',
                            'lineno': 42,
                            'column': 51,
                            'level': 'error',
                            'linter': 'flake8',
                            'rule': 'E001',
                            'message': 'dummy issue',
                        }
                    ]
                },
            }
        }
    }
    workflow = RemoteWorkflow(MockQueue(tasks))
    issues = workflow.run(mock_revision)
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, MozLintIssue)
    assert issue.path == 'test.cpp'
    assert issue.line == 42
    assert issue.column == 51
    assert issue.linter == 'flake8'
    assert issue.message == 'dummy issue'


def test_clang_tidy_task(mock_try_config, mock_revision):
    '''
    Test a remote workflow with a clang-tidy analyzer
    '''
    from static_analysis_bot.workflows.remote import RemoteWorkflow
    from static_analysis_bot.clang.tidy import ClangTidyIssue

    tasks = {
        'decision': {
            'image': 'taskcluster/decision:XXX',
            'env': {
                'GECKO_HEAD_REPOSITORY': 'https://hg.mozilla.org/try',
                'GECKO_HEAD_REV': 'deadbeef1234',
            }
        },
        'remoteTryTask': {
            'dependencies': ['clang-tidy']
        },
        'clang-tidy': {
            'name': 'source-test-clang-tidy',
            'state': 'completed',
            'artifacts': {
                'public/code-review/clang-tidy.json': {
                    'files': {
                        'test.cpp': {
                            'hash': 'e409f05a10574adb8d47dcb631f8e3bb',
                            'warnings': [
                                {
                                    'column': 12,
                                    'line': 123,
                                    'flag': 'checker.XXX',
                                    'message': 'some hard issue with c++',
                                    'filename': 'test.cpp',
                                }
                            ]
                        }
                    }
                },
            }
        }
    }
    workflow = RemoteWorkflow(MockQueue(tasks))
    issues = workflow.run(mock_revision)
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, ClangTidyIssue)
    assert issue.path == 'test.cpp'
    assert issue.line == 123
    assert issue.char == 12
    assert issue.check == 'checker.XXX'
    assert issue.message == 'some hard issue with c++'


def test_clang_format_task(mock_try_config, mock_revision):
    '''
    Test a remote workflow with a clang-format analyzer
    '''
    from static_analysis_bot.workflows.remote import RemoteWorkflow
    from static_analysis_bot.clang.format import ClangFormatIssue

    tasks = {
        'decision': {
            'image': 'taskcluster/decision:XXX',
            'env': {
                'GECKO_HEAD_REPOSITORY': 'https://hg.mozilla.org/try',
                'GECKO_HEAD_REV': 'deadbeef1234',
            }
        },
        'remoteTryTask': {
            'dependencies': ['clang-format']
        },
        'clang-format': {
            'name': 'source-test-clang-format',
            'state': 'completed',
            'artifacts': {
                'public/code-review/clang-format.json': {
                    'test.cpp': [
                        {
                            'line_offset': 11,
                            'char_offset': 44616,
                            'char_length': 7,
                            'lines_modified': 2,
                            'line': 1386,
                            'replacement': 'Multi\nlines',
                        }
                    ]
                }
            }
        }
    }
    workflow = RemoteWorkflow(MockQueue(tasks))
    issues = workflow.run(mock_revision)
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, ClangFormatIssue)
    assert issue.path == 'test.cpp'
    assert issue.line == 1386
    assert issue.nb_lines == 2
    assert issue.patch == 'Multi\nlines'
    assert issue.column == 11
    assert issue.as_dict() == {
        'analyzer': 'clang-format',
        'column': 11,
        'in_patch': False,
        'is_new': True,
        'line': 1386,
        'nb_lines': 2,
        'patch': 'Multi\nlines',
        'path': 'test.cpp',
        'publishable': False,
        'validates': False,
        'validation': {}
    }


def test_coverity_task(mock_try_config, mock_revision):
    '''
    Test a remote workflow with a clang-tidy analyzer
    '''
    from static_analysis_bot.workflows.remote import RemoteWorkflow
    from static_analysis_bot.coverity.coverity import CoverityIssue

    tasks = {
        'decision': {
            'image': 'taskcluster/decision:XXX',
            'env': {
                'GECKO_HEAD_REPOSITORY': 'https://hg.mozilla.org/try',
                'GECKO_HEAD_REV': 'deadbeef1234',
            }
        },
        'remoteTryTask': {
            'dependencies': ['coverity']
        },
        'coverity': {
            'name': 'source-test-coverity-coverity',
            'state': 'completed',
            'artifacts': {
                'public/code-review/coverity.json': {
                    'files': {
                        'test.cpp': {
                            'warnings': [
                                {
                                    'line': 66,
                                    'flag': 'UNINIT',
                                    'message': 'Using uninitialized value \"a\".',
                                    'extra': {
                                        'category': 'Memory - corruptions',
                                        'stateOnServer': {
                                            'presentInReferenceSnapshot': False
                                        },
                                        'stack': [
                                            {
                                                'line_number': 61,
                                                'description': 'Condition \"!target.oper…", taking false branch.',
                                                'file_path': 'dom/animation/Animation.cpp',
                                                'path_type': 'path'
                                            }
                                        ]
                                    }
                                }
                            ]
                        }
                    }
                },
            }
        }
    }
    workflow = RemoteWorkflow(MockQueue(tasks))
    issues = workflow.run(mock_revision)
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, CoverityIssue)
    assert issue.path == 'test.cpp'
    assert issue.line == 66
    assert issue.kind == 'UNINIT'
    assert issue.bug_type == 'Memory - corruptions'
    assert issue.message == 'Using uninitialized value \"a\".'
    assert issue.is_local()
    assert not issue.is_clang_error()
    assert issue.validates()


def test_infer_task(mock_try_config, mock_revision):
    '''
    Test a remote workflow with an infer analyzer
    '''
    from static_analysis_bot.workflows.remote import RemoteWorkflow
    from static_analysis_bot.infer.infer import InferIssue

    tasks = {
        'decision': {
            'image': 'taskcluster/decision:XXX',
            'env': {
                'GECKO_HEAD_REPOSITORY': 'https://hg.mozilla.org/try',
                'GECKO_HEAD_REV': 'deadbeef1234',
            }
        },
        'remoteTryTask': {
            'dependencies': ['infer']
        },
        'infer': {
            'name': 'source-test-infer-infer',
            'state': 'completed',
            'artifacts': {
                'public/code-review/infer.json': [
                    {
                         'bug_class': 'PROVER',
                         'kind': 'ERROR',
                         'bug_type': 'THREAD_SAFETY_VIOLATION',
                         'qualifier': 'Read/Write race.',
                         'severity': 'HIGH',
                         'visibility': 'user',
                         'line': 1196,
                         'column': -1,
                         'procedure': 'void Bad.Function(Test,int)',
                         'procedure_id': 'org.mozilla.geckoview.somewhere():void',
                         'procedure_start_line': 0,
                         'file': 'mobile/android/geckoview/src/main/java/org/mozilla/test.java',
                         'bug_trace': [
                             {
                                 'level': 0,
                                 'filename': 'mobile/android/geckoview/src/main/java/org/mozilla/test.java',
                                 'line_number': 1196,
                                 'column_number': -1,
                                 'description': '<Read trace>'
                             }
                         ],
                         'key': 'GeckoSession.java|test|THREAD_SAFETY_VIOLATION',
                         'node_key': '9c5d6d9028928346cc4fb44cced5dea1',
                         'hash': 'b008b0dd2b74e6036fa2105f7e54458e',
                         'bug_type_hum': 'Thread Safety Violation',
                         'censored_reason': '',
                         'access': 'reallyLongHash'
                     }
                ]
            }
        }
    }
    workflow = RemoteWorkflow(MockQueue(tasks))
    issues = workflow.run(mock_revision)
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, InferIssue)
    assert issue.path == 'mobile/android/geckoview/src/main/java/org/mozilla/test.java'
    assert issue.line == 1196
    assert issue.column == -1
    assert issue.bug_type == 'THREAD_SAFETY_VIOLATION'
    assert issue.kind == 'ERROR'
    assert issue.message == 'Read/Write race.'
    assert issue.body is None
    assert issue.nb_lines == 1
    assert issue.as_dict() == {
        'analyzer': 'infer',
        'body': None,
        'bug_type': 'THREAD_SAFETY_VIOLATION',
        'column': -1,
        'in_patch': False,
        'is_new': False,
        'kind': 'ERROR',
        'line': 1196,
        'message': 'Read/Write race.',
        'nb_lines': 1,
        'path': 'mobile/android/geckoview/src/main/java/org/mozilla/test.java',
        'publishable': False,
        'validates': True,
    }
