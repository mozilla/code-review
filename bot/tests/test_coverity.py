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
    assert issue.validates()

    # Testing it as_text
    assert issue.as_text() == 'Some dummy event'

    # Testing as_markdown
    issue.body = 'Dummy body'
    assert issue.as_markdown() == '''
## coverity error

- **Message**: Some dummy event
- **Location**: to/test.cpp:123
- **In patch**: yes
- **Coverity check**: Dummy Checker Name
- **Publishable **: yes
- **Is new**: yes

```
Dummy body
```
'''


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
    assert not issue.validates()
