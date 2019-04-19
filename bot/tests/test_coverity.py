# -*- coding: utf-8 -*-
import os

from conftest import MOCK_DIR


def test_coverity_empty(mock_config, mock_repository, mock_revision, mock_coverity):
    '''
    Test coverity empty output
    '''
    from static_analysis_bot.coverity.coverity import Coverity
    cov = Coverity()

    issues = cov.return_issues(os.path.join(MOCK_DIR, 'coverity-empty.json'), mock_revision)
    assert issues == []


def test_coverity_publishable(mock_config, mock_repository, mock_revision, mock_coverity):
    '''
    Test coverity complete issue & publishable
    '''
    from static_analysis_bot.coverity.coverity import Coverity
    cov = Coverity()

    # Real issues
    issues = cov.return_issues(os.path.join(MOCK_DIR, 'coverity.json'), mock_revision)

    # The list must have one element
    assert len(issues) == 1

    # Verify that each element has a sane value
    issue = issues[0]
    assert issue.path == 'to/test.cpp'
    assert issue.line == 123
    assert issue.bug_type == 'Dummy Category'
    assert issue.message == 'Some dummy event'

    # Assert it's local, hence publishable
    assert issue.is_local()
    assert not issue.is_clang_error()
    assert issue.validates()

    # Testing it as_text
    assert issue.as_text() == 'Some dummy event'

    # Testing as_markdown
    issue.body = 'Dummy body'
    assert issue.as_markdown() == '''
## coverity error

- **Message**: Some dummy event
- **Location**: to/test.cpp:123
- **Coverity check**: Dummy Checker Name
- **Publishable **: yes
- **Is Clang Error**: no
- **Is Local**: yes
- **Reliability**: unknown

```
Dummy body
```
'''

    # Testing as_dict
    assert issue.as_dict() == {
        'analyzer': 'Coverity',
        'body': 'Dummy body',
        'bug_type': 'Dummy Category',
        'in_patch': False,
        'is_local': True,
        'is_new': False,
        'kind': 'Dummy Checker Name',
        'reliabiloty': 'unknown',
        'line': 123,
        'message': 'Some dummy event',
        'nb_lines': 1,
        'path': 'to/test.cpp',
        'publishable': True,
        'validates': True,
        'validation': {
            'is_clang_error': False,
            'is_local': True,
        }
    }

    assert issue.as_phabricator_lint() == {
        'code': 'coverity.Dummy Checker Name',
        'description': 'Dummy body',
        'line': 123,
        'name': 'Some dummy event',
        'path': 'to/test.cpp',
        'severity': 'error',
    }


def test_coverity_silent(mock_config, mock_repository, mock_revision, mock_coverity):
    '''
    Test coverity silent issue
    '''
    from static_analysis_bot.coverity.coverity import Coverity
    cov = Coverity()

    # Real issues
    issues = cov.return_issues(os.path.join(MOCK_DIR, 'coverity-silent.json'), mock_revision)

    # The list must have one element
    assert len(issues) == 1

    # Verify that each element has a sane value
    issue = issues[0]
    assert issue.path == 'to/test.cpp'
    assert issue.line == 123
    assert issue.bug_type == 'Dummy Category'
    assert issue.message == 'Some dummy event'

    # Assert it's not local, hence does NOT validate
    assert not issue.is_local()
    assert not issue.is_clang_error()
    assert not issue.validates()

    # Testing as_dict
    assert issue.as_dict() == {
        'analyzer': 'Coverity',
        'body': None,
        'bug_type': 'Dummy Category',
        'in_patch': False,
        'is_local': False,
        'is_new': False,
        'kind': 'Dummy Checker Name',
        'reliabiloty': 'unknown',
        'line': 123,
        'message': 'Some dummy event',
        'nb_lines': 1,
        'path': 'to/test.cpp',
        'publishable': False,
        'validates': False,
        'validation': {
            'is_clang_error': False,
            'is_local': False,
        }
    }


def test_coverity_forward_issue(mock_config, mock_repository, mock_revision, mock_coverity):
    '''
    Test coverity issue forwarded by clang - build issue
    '''
    from static_analysis_bot.coverity.coverity import Coverity
    cov = Coverity()

    # Build issue forwarded by Clang
    issues = cov.return_issues(os.path.join(MOCK_DIR, 'coverity-bug.json'), mock_revision)

    # The list must have one element
    assert len(issues) == 1

    # Verify that the issue is forwarded by Clang as a clang diagnostic error
    issue = issues[0]

    assert issue.is_clang_error()
