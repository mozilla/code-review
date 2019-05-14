# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import pytest


def test_no_deps(mock_config, mock_revision, mock_workflow):
    '''
    Test an error occurs when no dependencies are found on root task
    '''
    mock_workflow.setup_mock_tasks({
        'decision': {
            'image': 'taskcluster/decision:XXX',
            'env': {
                'GECKO_HEAD_REPOSITORY': 'https://hg.mozilla.org/try',
                'GECKO_HEAD_REV': 'deadbeef1234',
            }
        },
        'remoteTryTask': {},
        'extra-task': {},
    })

    with pytest.raises(AssertionError) as e:
        mock_workflow.run(mock_revision)
    assert str(e.value) == 'No task dependencies to analyze'


def test_baseline(mock_config, mock_revision, mock_workflow):
    '''
    Test a normal remote workflow (aka Try mode)
    - current task with analyzer deps
    - an analyzer in failed status
    - with some issues in its log
    '''
    from static_analysis_bot.tasks.lint import MozLintIssue
    from static_analysis_bot.tasks.coverage import CoverageIssue

    # We run on a mock TC, with a try source
    assert mock_config.taskcluster.task_id == 'local instance'
    assert mock_config.try_task_id == 'remoteTryTask'

    mock_workflow.setup_mock_tasks({
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
        'zero-cov': {
            'route': 'project.releng.services.project.production.code_coverage_bot.latest',
            'artifacts': {
                'public/zero_coverage_report.json': {
                    'files': [
                        {
                            'uncovered': True,
                            'name': 'test.cpp',
                        }
                    ],
                },
            }
        },
    })
    issues = mock_workflow.run(mock_revision)

    assert len(issues) == 2
    issue = issues[0]
    assert isinstance(issue, MozLintIssue)
    assert issue.path == 'test.cpp'
    assert issue.line == 12
    assert issue.column == 1
    assert issue.message == 'strange issue'
    assert issue.rule == 'checker XXX'
    assert issue.revision is mock_revision
    assert issue.validates()

    issue = issues[1]
    assert isinstance(issue, CoverageIssue)
    assert issue.path == 'test.cpp'
    assert issue.message == 'This file is uncovered'
    assert issue.line == 0
    assert issue.validates()


def test_no_failed(mock_config, mock_revision, mock_workflow):
    '''
    Test a remote workflow without any failed tasks
    '''

    mock_workflow.setup_mock_tasks({
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
    })
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 0


def test_no_issues(mock_config, mock_revision, mock_workflow):
    '''
    Test a remote workflow without any issues in its artifacts
    '''

    mock_workflow.setup_mock_tasks({
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
    })
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 0


def test_unsupported_analyzer(mock_config, mock_revision, mock_workflow):
    '''
    Test a remote workflow with an unsupported analyzer (not mozlint)
    '''

    mock_workflow.setup_mock_tasks({
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
    })
    with pytest.raises(Exception) as e:
        mock_workflow.run(mock_revision)
    assert str(e.value) == 'Unsupported task custom-analyzer-from-vendor'


def test_decision_task(mock_config, mock_revision, mock_workflow):
    '''
    Test a remote workflow with different decision task setup
    '''

    mock_workflow.setup_mock_tasks({
        'decision': {
        },
        'remoteTryTask': {
        },
    })
    with pytest.raises(AssertionError) as e:
        mock_workflow.run(mock_revision)
    assert str(e.value) == 'Missing decision task'

    mock_workflow.setup_mock_tasks({
        'decision': {
            'image': 'anotherImage',
        },
        'remoteTryTask': {
        },
    })
    with pytest.raises(AssertionError) as e:
        mock_workflow.run(mock_revision)
    assert str(e.value) == 'Missing decision task'

    mock_workflow.setup_mock_tasks({
        'decision': {
            'image': {
                'from': 'taskcluster/decision',
                'tag': 'unsupported',
            }
        },
        'remoteTryTask': {
        },
    })
    with pytest.raises(AssertionError) as e:
        mock_workflow.run(mock_revision)
    assert str(e.value) == 'Missing decision task'

    mock_workflow.setup_mock_tasks({
        'decision': {
            'image': 'taskcluster/decision:XXX',
        },
        'remoteTryTask': {
        },
    })
    with pytest.raises(AssertionError) as e:
        mock_workflow.run(mock_revision)
    assert str(e.value) == 'Not the try repo in GECKO_HEAD_REPOSITORY'

    mock_workflow.setup_mock_tasks({
        'decision': {
            'image': 'taskcluster/decision:XXX',
            'env': {
                'GECKO_HEAD_REPOSITORY': 'https://hg.mozilla.org/try',
            }
        },
        'remoteTryTask': {
        },
    })
    with pytest.raises(AssertionError) as e:
        mock_workflow.run(mock_revision)
    assert str(e.value) == 'Missing try revision'
    assert mock_revision.mercurial_revision is None

    mock_workflow.setup_mock_tasks({
        'decision': {
            'image': 'taskcluster/decision:XXX',
            'env': {
                'GECKO_HEAD_REPOSITORY': 'https://hg.mozilla.org/try',
                'GECKO_HEAD_REV': 'someRevision'
            }
        },
        'remoteTryTask': {
        },
    })
    with pytest.raises(AssertionError) as e:
        mock_workflow.run(mock_revision)
    assert str(e.value) == 'No task dependencies to analyze'
    assert mock_revision.mercurial_revision is not None
    assert mock_revision.mercurial_revision == 'someRevision'


def test_mozlint_task(mock_config, mock_revision, mock_workflow):
    '''
    Test a remote workflow with a mozlint analyzer
    '''
    from static_analysis_bot.tasks.lint import MozLintIssue

    mock_workflow.setup_mock_tasks({
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
        },
    })
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, MozLintIssue)
    assert issue.path == 'test.cpp'
    assert issue.line == 42
    assert issue.column == 51
    assert issue.linter == 'flake8'
    assert issue.message == 'dummy issue'


def test_clang_tidy_task(mock_config, mock_revision, mock_workflow):
    '''
    Test a remote workflow with a clang-tidy analyzer
    '''
    from static_analysis_bot import Reliability
    from static_analysis_bot.tasks.clang_tidy import ClangTidyIssue

    mock_workflow.setup_mock_tasks({
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
                                    'reliability': 'high',
                                    'message': 'some hard issue with c++',
                                    'filename': 'test.cpp',
                                },
                                {
                                    'column': 51,
                                    'line': 987,
                                    'flag': 'checker.YYY',
                                    # No reliability !
                                    'message': 'some harder issue with c++',
                                    'filename': 'test.cpp',
                                }
                            ]
                        }
                    }
                },
            }
        },
    })
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 2
    issue = issues[0]
    assert isinstance(issue, ClangTidyIssue)
    assert issue.path == 'test.cpp'
    assert issue.line == 123
    assert issue.char == 12
    assert issue.check == 'checker.XXX'
    assert issue.reliability == Reliability.High
    assert issue.message == 'some hard issue with c++'

    issue = issues[1]
    assert isinstance(issue, ClangTidyIssue)
    assert issue.path == 'test.cpp'
    assert issue.line == 987
    assert issue.char == 51
    assert issue.check == 'checker.YYY'
    assert issue.reliability == Reliability.Unknown
    assert issue.message == 'some harder issue with c++'


def test_clang_format_task(mock_config, mock_revision, mock_workflow):
    '''
    Test a remote workflow with a clang-format analyzer
    '''
    from static_analysis_bot.tasks.clang_format import ClangFormatIssue

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
        },
    }
    mock_workflow.setup_mock_tasks(tasks)
    assert len(mock_revision.improvement_patches) == 0
    issues = mock_workflow.run(mock_revision)
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
    assert len(mock_revision.improvement_patches) == 0

    # Check diffs are reported as improvement patches
    tasks['clang-format']['artifacts']['public/code-review/clang-format.diff'] = 'A nice diff in here...'
    mock_workflow.setup_mock_tasks(tasks)
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 1
    assert len(mock_revision.improvement_patches) == 1
    patch = mock_revision.improvement_patches[0]
    assert patch.analyzer == 'clang-format'
    assert patch.content == 'A nice diff in here...'


def test_coverity_task(mock_config, mock_revision, mock_workflow):
    '''
    Test a remote workflow with a clang-tidy analyzer
    '''
    from static_analysis_bot import Reliability
    from static_analysis_bot.tasks.coverity import CoverityIssue

    mock_workflow.setup_mock_tasks({
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
                                    'reliability': 'high',
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
                        },
                        '/builds/worker/checkouts/gecko/dom/something.cpp': {
                            'warnings': [
                                {
                                    'line': 123,
                                    'flag': 'UNINIT',
                                    'reliability': 'high',
                                    'message': 'Some error here',
                                    'extra': {
                                        'category': 'Nice bug',
                                        'stateOnServer': {
                                            'presentInReferenceSnapshot': False
                                        },
                                    }
                                }
                            ]
                        }
                    }
                },
            }
        },
    })
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 2
    issue = issues[0]
    assert isinstance(issue, CoverityIssue)
    assert issue.path == 'test.cpp'
    assert issue.line == 66
    assert issue.kind == 'UNINIT'
    assert issue.reliability == Reliability.High
    assert issue.bug_type == 'Memory - corruptions'
    assert issue.message == '''Using uninitialized value "a".
The path that leads to this defect is:

- //dom/animation/Animation.cpp:61//:
-- `path: Condition \"!target.oper…", taking false branch.`.\n'''
    assert issue.is_local()
    assert not issue.is_clang_error()
    assert issue.validates()

    issue = issues[1]
    assert isinstance(issue, CoverityIssue)
    assert issue.path == 'dom/something.cpp'
    assert issue.line == 123
    assert issue.kind == 'UNINIT'
    assert issue.reliability == Reliability.High
    assert issue.bug_type == 'Nice bug'
    assert issue.message == 'Some error here'
    assert issue.is_local()
    assert not issue.is_clang_error()
    assert issue.validates()
    assert issue.as_text() == f'Checker reliability is high (false positive risk).\nSome error here'


def test_infer_task(mock_config, mock_revision, mock_workflow):
    '''
    Test a remote workflow with an infer analyzer
    '''
    from static_analysis_bot.tasks.infer import InferIssue

    mock_workflow.setup_mock_tasks({
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
                         'procedure_id': 'org.mozilla.geckoview.somewhere(, mock_workflow):void',
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
        },
    })
    issues = mock_workflow.run(mock_revision)
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


def test_no_tasks(mock_config, mock_revision, mock_workflow):
    '''
    Test a remote workflow with only a Gecko decision task as dep
    https://github.com/mozilla/release-services/issues/2055
    '''

    mock_workflow.setup_mock_tasks({
        'decision': {
            'image': 'taskcluster/decision:XXX',
            'env': {
                'GECKO_HEAD_REPOSITORY': 'https://hg.mozilla.org/try',
                'GECKO_HEAD_REV': 'deadbeef1234',
            },
            'name': 'Gecko Decision Task',
        },
        'remoteTryTask': {
            'dependencies': ['decision', 'someOtherDockerbuild']
        },
    })
    issues = mock_workflow.run(mock_revision)
    assert len(issues) == 0
