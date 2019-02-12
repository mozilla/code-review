# -*- coding: utf-8 -*-


def test_coverity(mock_config, mock_repository, mock_revision, mock_coverity, mock_coverity_empty_output, mock_coverity_output):
    '''
    Test coverity
    '''
    from static_analysis_bot.coverity.coverity import Coverity
    cov = Coverity()

    # Expected empty result
    issues = cov.return_issues(mock_coverity_empty_output, mock_revision)
    assert issues == []

    # Real issues
    issues = cov.return_issues(mock_coverity_output, mock_revision)

    # The list must have one element
    assert len(issues) == 1

    # Verify that each element has a sane value
    issue = issues[0]
    assert issue.path == 'to/test.cpp'
    assert issue.line == 123
    assert issue.bug_type == 'Dummy Category'
    assert issue.message == 'Some dummy event'

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
