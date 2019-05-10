# -*- coding: utf-8 -*-
from static_analysis_bot.tasks.coverage import ZeroCoverageTask


def test_coverage(mock_config, mock_revision, mock_coverage_artifact):
    task_status = {
        'task': {},
        'status': {},
    }
    cov = ZeroCoverageTask('covTaskId', task_status)

    mock_revision.files = [
        # Uncovered file
        'my/path/file1.cpp',
        # Covered file
        'my/path/file2.js',
        # Uncovered third-party file
        'test/dummy/thirdparty.c',
        # Uncovered header file
        'my/path/header.h',
    ]

    # Build fake lines.
    for path in mock_revision.files:
        mock_revision.lines[path] = [0]

    issues = cov.parse_issues(mock_coverage_artifact, mock_revision)

    # The list must have three elements
    assert len(issues) == 3

    # Verify that each element has a sane value
    issue = issues[0]
    assert issue.path == 'my/path/file1.cpp'
    assert issue.line == 0
    assert issue.message == 'This file is uncovered'
    assert str(issue) == 'my/path/file1.cpp'

    assert issue.validates()

    assert issue.as_dict() == {
        'analyzer': 'coverage',
        'path': 'my/path/file1.cpp',
        'line': 0,
        'message': 'This file is uncovered',
        'in_patch': True,
        'is_new': False,
        'is_third_party': False,
        'validates': True,
        'publishable': True,
    }
    assert issue.as_phabricator_lint() == {
        'code': 'coverage',
        'line': 0,
        'name': 'This file is uncovered',
        'path': 'my/path/file1.cpp',
        'severity': 'warning',
    }
    assert issue.as_text() == 'This file is uncovered'
    assert issue.as_markdown() == '''
## coverage problem

- **Path**: my/path/file1.cpp
- **Third Party**: no
- **Publishable**: yes

```
This file is uncovered
```
'''

    issue = issues[1]
    assert issue.path == 'test/dummy/thirdparty.c'
    assert issue.line == 0
    assert issue.message == 'This file is uncovered'
    assert str(issue) == 'test/dummy/thirdparty.c'

    assert issue.validates()

    assert issue.as_dict() == {
        'analyzer': 'coverage',
        'path': 'test/dummy/thirdparty.c',
        'line': 0,
        'message': 'This file is uncovered',
        'in_patch': True,
        'is_new': False,
        'is_third_party': True,
        'validates': True,
        'publishable': True,
    }
    assert issue.as_phabricator_lint() == {
        'code': 'coverage',
        'line': 0,
        'name': 'This file is uncovered',
        'path': 'test/dummy/thirdparty.c',
        'severity': 'warning',
    }
    assert issue.as_text() == 'This file is uncovered'
    assert issue.as_markdown() == '''
## coverage problem

- **Path**: test/dummy/thirdparty.c
- **Third Party**: yes
- **Publishable**: yes

```
This file is uncovered
```
'''

    issue = issues[2]
    assert issue.path == 'my/path/header.h'
    assert issue.line == 0
    assert issue.message == 'This file is uncovered'
    assert str(issue) == 'my/path/header.h'

    assert not issue.validates()

    assert issue.as_dict() == {
        'analyzer': 'coverage',
        'path': 'my/path/header.h',
        'line': 0,
        'message': 'This file is uncovered',
        'in_patch': True,
        'is_new': False,
        'is_third_party': False,
        'validates': False,
        'publishable': False,
    }
    assert issue.as_phabricator_lint() == {
        'code': 'coverage',
        'line': 0,
        'name': 'This file is uncovered',
        'path': 'my/path/header.h',
        'severity': 'warning',
    }
    assert issue.as_text() == 'This file is uncovered'
    assert issue.as_markdown() == '''
## coverage problem

- **Path**: my/path/header.h
- **Third Party**: no
- **Publishable**: no

```
This file is uncovered
```
'''
