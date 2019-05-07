# -*- coding: utf-8 -*-
import os

from cli_common.log import get_logger
from static_analysis_bot import COVERAGE
from static_analysis_bot import Issue
from static_analysis_bot.config import settings
from static_analysis_bot.task import AnalysisTask

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
        self.revision = revision
        self.path = path
        self.line = lineno and int(lineno) or 0
        self.message = message
        self.nb_lines = 1

    def __str__(self):
        return self.path

    def is_publishable(self):
        '''
        Coverage issues are always publishable, unless they are in header files
        '''
        return self.validates()

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


class ZeroCoverageTask(AnalysisTask):
    '''
    List all issues found by coverage analysis on specified files
    Uses the most recent data from the code coverage bot
    '''
    route = 'project.releng.services.project.production.code_coverage_bot.latest'
    artifacts = [
        'public/zero_coverage_report.json',
    ]

    def parse_issues(self, artifacts, revision):
        zero_coverage_files = {
            file_info['name']
            for artifact in artifacts.values()
            for file_info in artifact['files']
            if file_info['uncovered']
        }

        return [
            CoverageIssue(self.clean_path(path), 0, 'This file is uncovered', revision)
            for path in revision.files
            if path in zero_coverage_files
        ]
