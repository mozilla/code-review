# -*- coding: utf-8 -*-
import os

import requests

from cli_common.log import get_logger
from static_analysis_bot import COVERAGE
from static_analysis_bot import DefaultAnalyzer
from static_analysis_bot import Issue
from static_analysis_bot import stats
from static_analysis_bot.config import settings
from static_analysis_bot.revisions import Revision

logger = get_logger(__name__)

ISSUE_MARKDOWN = '''
## coverage problem

- **Path**: {path}
- **Third Party**: {third_party}
- **Publishable**: {publishable}

```
{message}
```
'''


class CoverageIssue(Issue):
    ANALYZER = COVERAGE

    def __init__(self, path, lineno, message, revision):
        # Ensure path is always relative to the repository
        self.path = path
        if self.path.startswith(settings.repo_dir):
            self.path = os.path.relpath(self.path, settings.repo_dir)

        full_path = os.path.join(settings.repo_dir, self.path)

        assert os.path.exists(full_path), \
            'Missing {} in repo {}'.format(self.path, settings.repo_dir)

        self.line = lineno and int(lineno) or 0
        with open(full_path) as f:
            self.nb_lines = sum(1 for line in f)
        self.message = message
        self.revision = revision

    def __str__(self):
        return self.path

    def validates(self):
        '''
        Coverage issues are always publishable, unless they are in header files
        '''
        _, ext = os.path.splitext(self.path)
        return ext.lower() in settings.cpp_extensions.union(settings.js_extensions)

    def as_text(self):
        '''
        Build the text content for reporters
        '''
        return self.message

    def as_markdown(self):
        '''
        Build the Markdown content for the debug email
        '''
        return ISSUE_MARKDOWN.format(
            path=self.path,
            message=self.message,
            third_party=self.is_third_party() and 'yes' or 'no',
            publishable=self.is_publishable() and 'yes' or 'no',
            is_new=self.is_new and 'yes' or 'no',
        )

    def as_dict(self):
        '''
        Outputs all available information into a serializable dict
        '''
        return {
            'analyzer': 'coverage',
            'path': self.path,
            'line': self.line,
            'nb_lines': self.nb_lines,
            'message': self.message,
            'is_third_party': self.is_third_party(),
            'in_patch': self.revision.contains(self),
            'is_new': self.is_new,
            'validates': self.validates(),
            'publishable': self.is_publishable(),
        }

    def as_phabricator_lint(self):
        '''
        Outputs a Phabricator lint result
        '''
        return {
            'name': self.message,
            'code': 'coverage',
            'severity': 'warning',
            'path': self.path,
            'line': self.line,
        }


class Coverage(DefaultAnalyzer):
    def can_run_before_patch(self):
        '''
        Coverage analysis should run only once, after the patch is applied.
        '''
        return False

    @stats.api.timed('runtime.coverage')
    def run(self, revision):
        '''
        List all issues found by coverage analysis on specified files
        '''
        assert isinstance(revision, Revision)

        # Download zero coverage report.
        r = requests.get('https://index.taskcluster.net/v1/task/project.releng.services.project.production.code_coverage_bot.latest/artifacts/public/zero_coverage_report.json')  # noqa
        r.raise_for_status()
        report = r.json()
        zero_coverage_files = set(file_info['name'] for file_info in report['files'] if file_info['uncovered'])

        issues = [
            CoverageIssue(path, 0, 'This file is uncovered', revision)
            for path in revision.files
            if path in zero_coverage_files
        ]

        stats.report_issues('coverage', issues)

        return issues
