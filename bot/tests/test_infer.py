# -*- coding: utf-8 -*-
import json
from collections import Counter

BAD_JAVA_INFER = '''public class bad {
  public void x() {
    String x = null;
    x.length();
  }
}
'''


def test_infer_parser(mock_config, mock_repository, mock_revision, mock_infer, mock_infer_output, mock_infer_issues):
    '''
    Test the infer (or mach static-analysis) parser
    '''
    from static_analysis_bot.infer.infer import Infer
    infer = Infer()

    # Empty Output, infer maybe failed
    infer_output = {}
    issues = infer.parse_issues(infer_output, mock_revision)
    assert issues == []

    # No issues
    infer_output = json.loads('[]')
    issues = infer.parse_issues(infer_output, mock_revision)
    assert issues == []

    # Real case
    issues = infer.parse_issues(json.loads(mock_infer_output), mock_revision)
    assert len(issues) == 6
    sep = '\n' + '-'*20 + '\n'
    summary = sep.join(issue.as_text() for issue in issues)
    summary.strip()
    assert summary == mock_infer_issues


def test_as_text(mock_revision):
    '''
    Test text export for InferIssue
    '''
    from static_analysis_bot.infer.infer import InferIssue
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
    from static_analysis_bot.infer.infer import InferIssue
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


def test_repeats(mock_infer, mock_infer_repeats, mock_revision, mock_config):
    '''
    Test repeated issues are removed through set usage
    '''

    from static_analysis_bot.infer.infer import Infer
    infer = Infer()

    issues = infer.parse_issues(json.loads(mock_infer_repeats), mock_revision)
    assert isinstance(issues, list)

    # We have 2 issues
    assert len(issues) == 2
    count = Counter(i.bug_type for i in issues)
    assert count['NULL_DEREFERENCE'] == 2

    # A set should remove repeats
    issues = set(issues)
    assert len(issues) == 1
    count = Counter(i.bug_type for i in issues)
    assert count['NULL_DEREFERENCE'] == 1
