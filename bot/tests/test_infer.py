# -*- coding: utf-8 -*-


def test_as_text(mock_revision):
    '''
    Test text export for InferIssue
    '''
    from static_analysis_bot.tasks.infer import InferIssue
    parts = {
        'file': 'path/to/file.java',
        'line': 3,
        'column': -1,
        'bug_type': 'SOMETYPE',
        'kind': 'SomeKindOfBug',
        'qualifier': 'Error on this line'
    }
    issue = InferIssue(parts, mock_revision)
    issue.body = 'Dummy body withUppercaseChars'

    expected = 'SomeKindOfBug: Error on this line [infer: SOMETYPE]'
    assert issue.as_text() == expected


def test_as_markdown(mock_revision):
    '''
    Test markdown generation for InferIssue
    '''
    from static_analysis_bot.tasks.infer import InferIssue
    parts = {
        'file': 'path/to/file.java',
        'line': 3,
        'column': -1,
        'bug_type': 'SOMETYPE',
        'kind': 'SomeKindOfBug',
        'qualifier': 'Error on this line'
    }
    issue = InferIssue(parts, mock_revision)
    issue.body = 'Dummy body'

    assert issue.as_markdown() == '''
## infer error

- **Message**: Error on this line
- **Location**: path/to/file.java:3:-1
- **In patch**: no
- **Infer check**: SOMETYPE
- **Publishable **: no
- **Is new**: no

```
Dummy body
```
'''
