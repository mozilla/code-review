# -*- coding: utf-8 -*-
import os.path
from collections import Counter

import pytest

BAD_CPP_SRC = '''#include <demo>
int \tmain(void){
 printf("plop");return 42;
}'''

BAD_CPP_DIFF = '''1,3c1,4
< #include <demo>
< int \tmain(void){
<  printf("plop");return 42;
---
> #include <demo>
> int main(void) {
>   printf("plop");
>   return 42;
'''

BAD_CPP_VALID = '''#include <demo>
int main(void) {
  printf("plop");
  return 42;
}'''

BAD_CPP_TIDY = '''
void assignment() {
  char *a = 0;
  char x = 0;
}

int *ret_ptr() {
  return 0;
}

void test(){
    int x;
    x = 1;
}
'''


def test_expanded_macros(mock_stats, test_cpp, mock_revision):
    '''
    Test expanded macros are detected by clang issue
    '''
    from static_analysis_bot.clang.tidy import ClangTidyIssue
    parts = ('test.cpp', '42', '51', 'error', 'dummy message', 'dummy-check')
    issue = ClangTidyIssue(parts, mock_revision)
    assert issue.is_problem()
    assert issue.line == 42
    assert issue.char == 51
    assert issue.notes == []
    assert issue.is_expanded_macro() is False

    # Add a note starting with "expanded from macro..."
    parts = ('test.cpp', '42', '51', 'note', 'expanded from macro Blah dummy.cpp', 'dummy-check-note')
    issue.notes.append(ClangTidyIssue(parts, mock_revision))
    assert issue.is_expanded_macro() is True

    # Add another note does not change it
    parts = ('test.cpp', '42', '51', 'note', 'This is not an expanded macro', 'dummy-check-note')
    issue.notes.append(ClangTidyIssue(parts, mock_revision))
    assert issue.is_expanded_macro() is True

    # But if we swap them, it does not work anymore
    issue.notes.reverse()
    assert issue.is_expanded_macro() is False


def test_clang_format(mock_config, mock_repository, mock_stats, mock_clang, mock_revision, mock_workflow):
    '''
    Test clang-format runner
    '''
    from static_analysis_bot.clang.format import ClangFormat, ClangFormatIssue
    from static_analysis_bot.config import settings

    # Write badly formatted c file
    bad_file = os.path.join(mock_config.repo_dir, 'dom', 'bad.cpp')
    os.makedirs(os.path.dirname(bad_file))
    with open(bad_file, 'w') as f:
        f.write(BAD_CPP_SRC)

    # Commit bad.cpp
    mock_repository.add(bad_file.encode('utf-8'))
    _, rev = mock_repository.commit(b'Bad file', user=b'Tester')

    # Get formatting issues
    cf = ClangFormat()
    mock_revision.files = ['dom/bad.cpp', ]
    mock_revision.lines = {
        'dom/bad.cpp': [1, 2, 3],
    }
    issues = cf.run(mock_revision)

    # Small file, only one issue which group changes
    assert isinstance(issues, list)
    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, ClangFormatIssue)
    assert issue.is_publishable()

    assert issue.path == 'dom/bad.cpp'
    assert issue.line == 2
    assert issue.nb_lines == 2

    # At the end of the process, original file is patched
    assert open(bad_file).read() == BAD_CPP_VALID

    # Ensure the raw output dump exists
    clang_output_path = os.path.join(
        settings.taskcluster.results_dir,
        '{}-clang-format.txt'.format(repr(mock_revision)),
    )
    assert os.path.isfile(clang_output_path)

    # Test stats
    mock_stats.flush()
    metrics = mock_stats.get_metrics('issues.clang-format')
    assert len(metrics) == 1
    assert metrics[0][1]

    metrics = mock_stats.get_metrics('issues.clang-format.publishable')
    assert len(metrics) == 1
    assert metrics[0][1]

    metrics = mock_stats.get_metrics('runtime.clang-format.avg')
    assert len(metrics) == 1
    assert metrics[0][1] > 0

    # Cleanup the repo
    mock_repository.update(rev, clean=True)


def test_clang_tidy(mock_repository, mock_config, mock_clang, mock_stats, mock_revision):
    '''
    Test clang-tidy runner
    '''
    from static_analysis_bot.clang.tidy import ClangTidy, ClangTidyIssue
    from static_analysis_bot.config import settings

    # Init clang tidy runner
    ct = ClangTidy()

    # Write badly formatted c file
    bad_file = os.path.join(mock_config.repo_dir, 'bad.cpp')
    with open(bad_file, 'w') as f:
        f.write(BAD_CPP_TIDY)

    # Get issues found by clang-tidy
    mock_revision.files = ['bad.cpp', ]
    mock_revision.lines = {
        'bad.cpp': range(len(BAD_CPP_TIDY.split('\n'))),
    }
    issues = ct.run(mock_revision)
    assert len(issues) == 3
    assert isinstance(issues[0], ClangTidyIssue)
    assert issues[0].check == 'modernize-use-nullptr'
    assert issues[0].reason == 'Modernize our code base to C++11'
    assert issues[0].line == 3
    assert isinstance(issues[1], ClangTidyIssue)
    assert issues[1].check == 'modernize-use-nullptr'
    assert issues[1].reason == 'Modernize our code base to C++11'
    assert issues[1].line == 8
    assert isinstance(issues[2], ClangTidyIssue)
    assert issues[2].check == 'clang-analyzer-deadcode.DeadStores'
    assert issues[2].reason is None
    assert issues[2].line == 13

    # Ensure the raw output dump exists
    clang_output_path = os.path.join(
        settings.taskcluster.results_dir,
        '{}-clang-tidy.txt'.format(repr(mock_revision)),
    )
    assert os.path.isfile(clang_output_path)

    # Test stats
    mock_stats.flush()
    metrics = mock_stats.get_metrics('issues.clang-tidy')
    assert len(metrics) == 1
    assert metrics[0][1] == 3

    metrics = mock_stats.get_metrics('issues.clang-tidy.publishable')
    assert len(metrics) == 1
    assert metrics[0][1] == 3

    metrics = mock_stats.get_metrics('runtime.clang-tidy.avg')
    assert len(metrics) == 1
    assert metrics[0][1] > 0


def test_clang_tidy_checks(mock_config, mock_repository, mock_clang):
    '''
    Test that all our clang-tidy checks actually exist
    '''
    from static_analysis_bot.clang.tidy import ClangTidy
    from static_analysis_bot.config import CONFIG_URL, settings

    # Get the set of all available checks that the local clang-tidy offers
    clang_tidy = ClangTidy(validate_checks=False)

    # Verify that Firefox's clang-tidy configuration actually specifies checks
    assert len(settings.clang_checkers) > 0, \
        'Firefox clang-tidy configuration {} should specify > 0 clang_checkers'.format(CONFIG_URL)

    # Verify that the specified clang-tidy checks actually exist
    missing = clang_tidy.list_missing_checks()
    assert len(missing) == 0, \
        'Missing clang-tidy checks: {}'.format(', '.join(missing))


def test_clang_tidy_parser(mock_config, mock_repository, mock_revision, mock_clang_output, mock_clang_issues):
    '''
    Test the clang-tidy (or mach static-analysis) parser
    '''
    from static_analysis_bot.clang.tidy import ClangTidy
    clang_tidy = ClangTidy()

    # Empty Output
    clang_output = 'Nothing.'
    issues = clang_tidy.parse_issues(clang_output, mock_revision)
    assert issues == []

    # No warnings
    clang_output = 'Whatever text.\n0 warnings present.'
    issues = clang_tidy.parse_issues(clang_output, mock_revision)
    assert issues == []

    # One warning, but no header
    clang_output = 'Whatever text.\n1 warnings present.'
    with pytest.raises(Exception):
        clang_tidy.parse_issues(clang_output, mock_revision)

    # One warning, One header
    clang_output = '/path/to/test.cpp:42:39: error: methods annotated with MOZ_NO_DANGLING_ON_TEMPORARIES cannot be && ref-qualified [mozilla-dangling-on-temporary]'  # noqa
    clang_output += '\n1 warnings present.'
    issues = clang_tidy.parse_issues(clang_output, mock_revision)
    assert len(issues) == 1
    assert issues[0].path == '/path/to/test.cpp'
    assert issues[0].line == 42
    assert issues[0].check == 'mozilla-dangling-on-temporary'

    # Real case
    issues = clang_tidy.parse_issues(mock_clang_output, mock_revision)
    assert len(issues) == 13
    sep = '\n' + '-'*20 + '\n'
    summary = sep.join(issue.as_text() for issue in issues)
    assert summary == mock_clang_issues


def test_as_text(mock_revision):
    '''
    Test text export for ClangTidyIssue
    '''
    from static_analysis_bot.clang.tidy import ClangTidyIssue
    parts = ('test.cpp', '42', '51', 'error', 'dummy message withUppercaseChars', 'dummy-check')
    issue = ClangTidyIssue(parts, mock_revision)
    issue.body = 'Dummy body withUppercaseChars'

    assert issue.as_text() == 'Error: Dummy message withUppercaseChars [clang-tidy: dummy-check]\n```\nDummy body withUppercaseChars\n```'


def test_as_markdown(mock_revision):
    '''
    Test markdown generation for ClangTidyIssue
    '''
    from static_analysis_bot.clang.tidy import ClangTidyIssue
    parts = ('test.cpp', '42', '51', 'error', 'dummy message', 'dummy-check')
    issue = ClangTidyIssue(parts, mock_revision)
    issue.body = 'Dummy body'

    assert issue.as_markdown() == '''
## clang-tidy error

- **Message**: dummy message
- **Location**: test.cpp:42:51
- **In patch**: no
- **Clang check**: dummy-check
- **Publishable check**: no
- **Third Party**: no
- **Expanded Macro**: no
- **Publishable **: no
- **Is new**: no

```
Dummy body
```


'''


def test_repeats(mock_clang_repeats, mock_revision, mock_config):
    '''
    Test repeated issues are removed through set usage
    '''

    from static_analysis_bot.clang.tidy import ClangTidy
    clang_tidy = ClangTidy()

    issues = clang_tidy.parse_issues(mock_clang_repeats, mock_revision)
    assert isinstance(issues, list)

    # We have 2 issues for modernize-loop-convert
    # on the same file/line/char
    assert len(issues) == 4
    count = Counter(i.check for i in issues)
    assert count['modernize-loop-convert'] == 2

    # A set should remove repeats
    issues = set(issues)
    assert len(issues) == 3
    count = Counter(i.check for i in issues)
    assert count['modernize-loop-convert'] == 1


def test_clang_format_3rd_party(mock_repository, mock_revision):
    '''
    Test a clang format issue in 3rd party is not publishable
    '''
    from static_analysis_bot.clang.format import ClangFormatIssue

    mock_revision.lines = {
        'test/not_3rd.c': [10, ],
        'test/dummy/third_party.c': [10, ],
    }
    issue = ClangFormatIssue('test/not_3rd.c', 10, 1, mock_revision)
    assert issue.is_publishable()

    # test/dummy is a third party directory
    issue = ClangFormatIssue('test/dummy/third_party.c', 10, 1, mock_revision)
    assert not issue.is_publishable()
