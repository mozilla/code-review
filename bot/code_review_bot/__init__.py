# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import abc
import enum
import hashlib
import json

import requests
import structlog

from code_review_bot.config import Publication
from code_review_bot.config import settings
from code_review_bot.stats import InfluxDb
from code_review_tools.taskcluster import TaskclusterConfig

logger = structlog.get_logger(__name__)

CLANG_TIDY = "clang-tidy"
CLANG_FORMAT = "clang-format"
MOZLINT = "mozlint"
INFER = "infer"
COVERAGE = "coverage"
COVERITY = "coverity"


class AnalysisException(Exception):
    """
    Custom exception used in controlled errors
    """

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class Issue(abc.ABC):
    """
    Common reported issue interface
    """

    is_new = False
    revision = None

    def __init__(
        self,
        analyzer: str,
        revision,
        path: str,
        line: int,
        nb_lines: int,
        check: str,
        column: int = None,
        message: str = None,
        level: str = "error",
    ):
        # Check while avoiding circular dependencies
        from code_review_bot.revisions import Revision

        assert isinstance(revision, Revision)

        # Base required fields for all issues
        self.revision = revision
        self.analyzer = analyzer
        self.check = check
        self.path = path
        self.line = line
        self.nb_lines = nb_lines
        self.check = check

        # Optional common fields
        self.column = column
        self.message = message
        self.level = level

    def __str__(self):
        return f"{self.analyzer} issue {self.check}@{self.level} {self.path} line {self.line}"

    def build_extra_identifiers(self):
        """
        Used to add information when building an issue unique hash
        """
        return {}

    def is_publishable(self):
        """
        Is this issue publishable on reporters ?
        Supports both publication mode
        """
        assert self.revision is not None, "Missing revision"

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

        raise Exception("Unsupported publication mode {}".format(settings.publication))

    def build_hash(self):
        """
        Build a uniquely identifying hash for that issue
        """
        assert self.revision is not None, "Missing revision"

        try:
            # Load all the lines affected by the issue
            file_content = self.revision.load_file(self.path)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(
                    "Failed to download a file with an issue", path=self.path
                )

                # We still build the hash with empty content
                file_content = ""
            else:
                # When encountering another HTTP error, raise the issue
                raise

        # Build raw content:
        # 1. lines affected by patch
        # 2. without any spaces around each line
        file_lines = file_content.splitlines()
        start = self.line - 1  # file_lines start at 0, not 1
        raw_content = "\n".join(
            [
                line.strip()
                for line in file_lines[start : start + self.nb_lines]  # noqa E203
            ]
        )

        # Build hash payload using issue data
        # excluding file position information (lines & char)
        extras = json.dumps(self.build_extra_identifiers(), sort_keys=True)
        payload = ":".join(
            [self.analyzer, self.path, self.level, self.check, extras, raw_content]
        ).encode("utf-8")

        # Finally build the MD5 hash
        return hashlib.md5(payload).hexdigest()

    @abc.abstractmethod
    def validates(self):
        """
        Is this issue publishable on reporters using IN_PATCH publication ?
        Should check specific rules and return a boolean
        """
        raise NotImplementedError

    @abc.abstractmethod
    def as_text(self):
        """
        Build the text content for reporters
        """
        raise NotImplementedError

    @abc.abstractmethod
    def as_markdown(self):
        """
        Build the Markdown content for debug email
        """
        raise NotImplementedError

    def as_error(self):
        """
        Build the Markdown content for for build error issues
        """
        raise NotImplementedError

    def as_dict(self):
        """
        Build the serializable dict representation of the issue
        Used by debugging tools
        """
        return {
            "analyzer": self.analyzer,
            "path": self.path,
            "line": self.line,
            "nb_lines": self.nb_lines,
            "column": self.column,
            "check": self.check,
            "level": self.level,
            "message": self.message,
            "in_patch": self.revision.contains(self),
            "is_new": self.is_new,
            "validates": self.validates(),
            "publishable": self.is_publishable(),
            "hash": self.build_hash(),
        }

    @abc.abstractmethod
    def as_phabricator_lint(self):
        """
        Build the Phabricator LintResult instance
        Used by the HarborMaster reporter
        """
        raise NotImplementedError

    def as_phabricator_unitresult(self):
        """
        Build a Phabricator UnitResult to publish through Harbormaster API
        """
        raise NotImplementedError

    def is_build_error(self):
        """
        Is this issue a build error?
        Default is False
        """
        return False


class Reliability(enum.Enum):
    Unknown = "unknown"
    High = "high"
    Medium = "medium"
    Low = "low"

    @property
    def invert(self):
        """
        Verbalize the opposite of `value` of reliability to be used in coherent
        sentences.
        """
        inversions = {"high": "low", "medium": "medium", "low": "high"}

        return inversions.get(self.value, "unknown")


# Create common stats instance
stats = InfluxDb()

# Create common taskcluster config
taskcluster = TaskclusterConfig()
