# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from static_analysis_bot.config import settings
from static_analysis_bot.config import Publication
from static_analysis_bot.stats import Datadog
import itertools
import hashlib
import json
import os
import abc

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


class DefaultAnalyzer(abc.ABC):
    '''
    Default base analzer that must be implemented by each analyzer in particular
    '''
    @abc.abstractmethod
    def run(self, revision):
        '''
        The run procedure that each analyzer must implement, this is the entry
        point where the execution of the checker starts
        '''
        raise NotImplementedError

    def can_run_before_patch(self):
        '''
        By default an analyzer can be ran two times, before the patch is applied
        and after. By there are special cases where this behaviour is not wanted,
        hence it must be reflected in the re-implementation of this method.
        '''
        return True


class Issue(abc.ABC):
    '''
    Common reported issue interface

    Several properties are also needed:
    - repo_dir: Mercurial repository directory
    - path: Source file path relative to repo_dir
    - line: Line where the issue begins
    - nb_lines: Number of lines affected by the issue
    '''
    lines_hash = None
    is_new = False
    revision = None

    def __eq__(self, other):
        return self.__hash__() == other.__hash__()

    def __hash__(self):
        '''
        Unique issue identifier, used to compare issues
        '''
        if self.lines_hash is None:
            self.build_lines_hash()

        payload = {
            'class': self.__class__.__name__,
            'path': self.path,
            'lines_hash': self.lines_hash,
        }
        payload.update(self.build_extra_identifiers())
        return hash(json.dumps(payload, sort_keys=True))

    def build_lines_hash(self):
        '''
        Build a unique hash to identify lines related to this issue
        Skip leading spaces to have same hashes when only the indentation changes
        '''
        assert settings.has_local_clone, 'Cannot build lines hash without a local clone'

        # Read issue related content here to build an hash
        full_path = os.path.join(settings.repo_dir, self.path)
        assert os.path.exists(full_path), \
            'Missing file {}'.format(full_path)

        # Only read necessary lines
        with open(full_path) as source:
            start = max(self.line - 1, 0)
            end = start + self.nb_lines
            lines = itertools.islice(source, start, end)
            content = ''.join(l.lstrip() for l in lines)

        # Build the content hash
        self.lines_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        return self.lines_hash

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
            return self.is_new

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

    def is_third_party(self):
        '''
        Is this issue in a third party path ?
        Once we are using only try, we should not need this check anymore
        '''
        if not settings.has_local_clone:
            return False

        # List third party directories using mozilla-central file
        full_path = os.path.join(settings.repo_dir, settings.third_party)
        assert os.path.exists(full_path), \
            'Missing third party file {}'.format(full_path)
        with open(full_path) as f:
            # Remove new lines
            third_parties = list(map(lambda l: l.rstrip(), f.readlines()))

        for path in third_parties:
            if self.path.startswith(path):
                return True
        return False


# Create common stats instance
stats = Datadog()
