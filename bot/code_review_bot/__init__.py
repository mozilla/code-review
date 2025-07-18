# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import abc
import enum
import hashlib
import json
import os
from functools import cached_property

import requests
import structlog
from libmozdata.phabricator import LintResult, UnitResult, UnitResultState
from taskcluster.helper import TaskclusterConfig

from code_review_bot.config import settings
from code_review_bot.stats import InfluxDb
from code_review_bot.tasks.base import AnalysisTask

logger = structlog.get_logger(__name__)


def positive_int(name, x):
    """Helper to get a positive integer or None"""
    if isinstance(x, int):
        if x >= 0:
            return x
        else:
            logger.warning(f"Negative {name} value found, defaults to None", value=x)
    return None


class AnalysisException(Exception):
    """
    Custom exception used in controlled errors
    """

    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class InvalidTrigger(Exception):
    """
    Raised when the bot has been started with an invalid trigger
    Main reason is a gecko-level-3 task not being a build (cron, ...)
    """


class InvalidRepository(Exception):
    """
    Raised when the bot has been started on a build task from
    an unsupported repository
    """


class Level(enum.Enum):
    # A critical issue breaks CI and must always be reported
    Error = "error"

    # Warnings are reported when they are in patch
    Warning = "warning"


class Issue(abc.ABC):
    """
    Common reported issue interface
    """

    revision = None

    def __init__(
        self,
        analyzer: AnalysisTask,
        revision,
        path: str,
        line: int,
        nb_lines: int,
        check: str,
        column: int = None,
        message: str = None,
        level: Level = Level.Warning,
        fix: str = None,
        language: str = None,
    ):
        # Check while avoiding circular dependencies
        from code_review_bot.revisions import Revision

        assert isinstance(revision, Revision)
        assert isinstance(analyzer, AnalysisTask)

        # Base required fields for all issues
        assert not os.path.isabs(path), f"Issue path can not be absolute {path}"
        self.revision = revision
        self.analyzer = analyzer
        self.check = check
        self.path = path
        self.line = positive_int("line", line)
        self.nb_lines = positive_int("nb_lines", nb_lines)

        # Support line 0 for full file issues like `source-test-mozlint-test-manifest`.
        if self.line == 0:
            logger.info("Line 0 is not supported, falling back to full file issue")
            self.line = None

        # Optional common fields
        self.column = column
        self.message = message
        self.level = level

        # Reserved payload for backend
        self.on_backend = None

        # Store information when a fix is available
        self.fix = fix
        self.language = language
        if self.fix is not None:
            assert self.language is not None, "Missing fix language"

        # Mark the issue as known by default, so only errors are reported
        # The before/after feature may tag some issues as new, so they are reported
        self.new_issue = False

    def __str__(self):
        line = f"line {self.line}" if self.line is not None else "full file"
        return f"{self.analyzer.name} issue {self.check}@{self.level.value} {self.path} {line}"

    @property
    def display_name(self):
        """
        Issue's base name (by default analyzer's name)
        But can be overridden by subclasses
        """
        return self.analyzer.display_name

    def build_extra_identifiers(self):
        """
        Used to add information when building an issue unique hash
        """
        return {}

    @property
    def allow_before_and_after_publish(self):
        """
        Allow the possibility for an issue to avoid being published based on before/after.
        This allow publishing issues based on other criteria, like in_patch.
        """
        if taskcluster.secrets.get(
            f"{self.analyzer.name.upper()}_DISABLE_PUBLICATION_BEFORE_AFTER", False
        ):
            return False

        return self.revision.before_after_feature

    def is_publishable(self):
        """
        Is this issue publishable on reporters ?
        """
        assert self.revision is not None, "Missing revision"

        # Always check specific rules validate
        if not self.validates():
            return False

        if self.allow_before_and_after_publish:
            # Only publish new issues or issues inside the diff
            return self.new_issue or self.in_patch

        # An error is always published
        if self.level == Level.Error:
            return True

        # Then check if the backend marks this issue as publishable
        if self.on_backend is not None:
            return self.on_backend["publishable"]

        # Fallback to in_patch detection
        return self.in_patch

    @property
    def in_patch(self):
        return self.revision.contains(self)

    @cached_property
    def hash(self):
        """
        Build a unique hash identifying that issue and cache the resulting value
        The text concerned by the issue is used and not its position in the file
        Message content is hashed as a single linter may return multiple issues on a single line
        We make the assumption that the message does not contain the line number
        If an error occurs reading the file content (locally or remotely), None is returned
        """
        assert self.revision is not None, "Missing revision"

        # Build the hash only if the file is not autogenerated.
        # An autogenerated file resides in the build directory that it has the
        #  format `obj-x86_64-pc-linux-gnu`
        file_content = None
        if "/obj-" not in self.path:
            if settings.mercurial_cache_checkout:
                logger.debug("Using the local repository to build issue's hash")
                try:
                    with (settings.mercurial_cache_checkout / self.path).open() as f:
                        file_content = f.read()
                except (FileNotFoundError, IsADirectoryError):
                    logger.warning(
                        "Failed to find issue's related file", path=self.path
                    )
                    file_content = None
            else:
                try:
                    # Load all the lines affected by the issue
                    file_content = self.revision.load_file(self.path)
                except ValueError:
                    # Build the hash with an empty content in case the path is erroneous
                    file_content = None
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 404:
                        logger.warning(
                            "Failed to download a file with an issue", path=self.path
                        )

                        # We still build the hash with empty content
                        file_content = None
                    else:
                        # When encountering another HTTP error, raise the issue
                        raise

        if file_content is None:
            self._hash = None
            return self._hash

        # Build raw content:
        # 1. lines affected by patch
        # 2. without any spaces around each line
        file_lines = file_content.splitlines()

        if self.line is None or self.nb_lines is None:
            # Use full file when line is not specified
            lines = file_lines

        else:
            # Use a range of lines
            start = self.line - 1  # file_lines start at 0, not 1
            lines = file_lines[start : start + self.nb_lines]
        raw_content = "\n".join([line.strip() for line in lines])

        # Build hash payload using issue data
        # excluding file position information (lines & char)
        extras = json.dumps(self.build_extra_identifiers(), sort_keys=True)
        payload = ":".join(
            [
                self.analyzer.name,
                self.path,
                self.level.value,
                self.check,
                extras,
                raw_content,
                self.message,
            ]
        ).encode("utf-8")

        # Finally build the MD5 hash
        return hashlib.md5(payload).hexdigest()

    @cached_property
    def file_exists(self):
        """
        Check if the file that generated the issue still exists after applying the patch.
        """
        if settings.mercurial_cache_checkout:
            logger.debug(
                "Using the local repository to check if the file that caused the issue still exists."
            )
            return (settings.mercurial_cache_checkout / self.path).exists()
        else:
            # It is not possible to use revision.has_file directly because it returns file that have been modified
            try:
                content = self.revision.load_file(self.path)
                return content != ""
            except requests.exceptions.HTTPError as e:
                if e.response.status_code != 404:
                    raise e
                return False

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
        issue_hash = None
        try:
            issue_hash = self.hash
        except Exception as e:
            logger.warn("Failed to build issue hash", error=str(e), issue=str(self))

        return {
            "analyzer": self.analyzer.name,
            "path": self.path,
            "line": self.line,
            "nb_lines": self.nb_lines,
            "column": self.column,
            "check": self.check,
            "level": self.level.value,
            "message": self.message,
            "in_patch": self.in_patch,
            "validates": self.validates(),
            "publishable": self.is_publishable(),
            "hash": issue_hash,
            "fix": self.fix,
        }

    def as_phabricator_lint(self):
        """
        Build the Phabricator LintResult instance
        """
        # Add the level to the issue message
        if self.level == Level.Error:
            # We use the IMPORTANT red block silently
            prefix = "(IMPORTANT) ERROR:"
        else:
            prefix = "WARNING:"
        description = f"{prefix} {self.message}"

        # Add a fix when available
        # Prefix each line with 2 spaces as required by phabricator to trigger a code block
        # with syntax highlighting
        if self.fix is not None:
            fix = "\n".join(f"  {line}" for line in self.fix.splitlines())
            description += f"\n\n  lang={self.language}\n{fix}"

        return LintResult(
            name=self.display_name,
            description=description,
            code=self.check,
            severity=self.level.value,
            path=self.path,
            # Report full file issues on line 1
            line=self.line if self.line is not None else 1,
            char=self.column,
        )

    def as_phabricator_unitresult(self):
        """
        Build a Phabricator UnitResult for build errors
        """
        assert (
            self.is_build_error()
        ), "Only build errors may be published as unit results"

        return UnitResult(
            namespace="code-review",
            name="general",
            result=UnitResultState.Fail,
            details=f"Code review bot found a **build error**: \n{self.message}",
            format="remarkup",
        )

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
taskcluster = TaskclusterConfig("https://firefox-ci-tc.services.mozilla.com")
