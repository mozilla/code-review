# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import abc
import enum

from static_analysis_bot.config import Publication
from static_analysis_bot.config import settings
from static_analysis_bot.stats import Datadog

CLANG_TIDY = 'clang-tidy'
CLANG_FORMAT = 'clang-format'
MOZLINT = 'mozlint'
INFER = 'infer'
COVERAGE = 'coverage'
COVERITY = 'coverity'


class AnalysisException(Exception):
    '''
    Custom exception used in controlled errors
    '''
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class Issue(abc.ABC):
    '''
    Common reported issue interface

    Several properties are also needed:
    - path: Source file path relative to repo
    - line: Line where the issue begins
    - nb_lines: Number of lines affected by the issue
    '''
    lines_hash = None
    is_new = False
    revision = None

    def build_extra_identifiers(self):
        '''
        Used to compare with same-class issues
        '''
        return {}

    def is_publishable(self):
        '''
        Is this issue publishable on reporters ?
        Supports both publication mode
        '''
        assert self.revision is not None, \
            'Missing revision'

        # Always check specific rules validate
        if not self.validates():
            return False

        if settings.publication == Publication.IN_PATCH:
            # Only check that the issue is in this revision
            return self.revision.contains(self)

        if settings.publication == Publication.BEFORE_AFTER:
            # Simply use marker set on workflow
            # and check the revision contains the file
            # as Phabricator only support inline comments on modified files
            return self.revision.has_file(self.path) and self.is_new

        raise Exception('Unsupported publication mode {}'.format(settings.publication))

    @abc.abstractmethod
    def validates(self):
        '''
        Is this issue publishable on reporters using IN_PATCH publication ?
        Should check specific rules and return a boolean
        '''
        raise NotImplementedError

    @abc.abstractmethod
    def as_text(self):
        '''
        Build the text content for reporters
        '''
        raise NotImplementedError

    @abc.abstractmethod
    def as_markdown(self):
        '''
        Build the Markdown content for debug email
        '''
        raise NotImplementedError

    @abc.abstractmethod
    def as_dict(self):
        '''
        Build the serializable dict representation of the issue
        Used by debugging tools
        '''
        raise NotImplementedError

    @abc.abstractmethod
    def as_phabricator_lint(self):
        '''
        Build the Phabricator LintResult instance
        Used by the HarborMaster reporter
        '''
        raise NotImplementedError

    def is_third_party(self):
        '''
        Is this issue in a third party path ?
        '''
        return settings.is_third_party(self.path)


class Reliability(enum.Enum):
    Unknown = 'unknown'
    High = 'high'
    Medium = 'medium'
    Low = 'low'


# Create common stats instance
stats = Datadog()
