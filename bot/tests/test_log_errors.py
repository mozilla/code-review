import os

import pytest
from conftest import FIXTURES_DIR

from code_review_bot.tasks.log_errors import (
    MAX_LINE_LENGTH,
    extract_error_lines,
    format_error_lines,
    is_error_line,
)

BUILD_FAILURE_LOG = os.path.join(FIXTURES_DIR, "build_failure_live_backing.log")


@pytest.mark.parametrize(
    "line, expected",
    [
        ("/src/foo.cpp:12:3: error: something broke", True),
        ("gmake[4]: *** [rules.mk:669: foo.o] Error 1", True),
        ("13:10:50    ERROR - 'mach build -v' did not run successfully.", True),
        ("13:10:45     INFO -  ValueError: bad value", True),
        ("TEST-UNEXPECTED-FAIL | test_foo.js | assertion failed", True),
        ("[taskcluster:error] exit status 255", True),
        ("TEST-INFO | something fatal error-like", False),
        ("13:10:45     INFO -  warning: non-fatal error here", False),
        ("compiling foo.cpp", False),
    ],
)
def test_is_error_line(line, expected):
    assert is_error_line(line) is expected


def test_extract_error_lines_from_build_log():
    with open(BUILD_FAILURE_LOG, "rb") as f:
        lines = extract_error_lines(f)

    assert lines == [
        "/builds/worker/checkouts/gecko/dom/media/webaudio/AudioSinkInfo.h:18:1: error: final class 'AudioSinkInfo' uses NS_DECL_CYCLE_COLLECTING_ISUPPORTS",
        "/builds/worker/checkouts/gecko/dom/media/webaudio/AudioContext.cpp:899:21: error: arguments must all be strong refs",
        "'mach build -v' did not run successfully. Please check log for errors.",
        "[taskcluster:error] exit status 255",
    ]


def test_extract_error_lines_keeps_make_errors_when_alone():
    lines = extract_error_lines(
        [
            "gmake[4]: *** [rules.mk:669: foo.o] Error 1",
            "gmake[4]: *** [rules.mk:669: foo.o] Error 1",
            "gmake[3]: *** [recurse.mk:72: target-objects] Error 2",
        ]
    )

    assert lines == [
        "gmake[4]: *** [rules.mk:669: foo.o] Error 1",
        "gmake[3]: *** [recurse.mk:72: target-objects] Error 2",
    ]


def test_extract_error_lines_without_errors():
    assert extract_error_lines(["compiling foo.cpp", "linking libxul.so"]) == []


def test_extract_error_lines_max_lines():
    lines = extract_error_lines(
        [f"/src/foo.cpp:{i}:1: error: broken" for i in range(10)], max_lines=3
    )

    assert lines == [
        "/src/foo.cpp:0:1: error: broken",
        "/src/foo.cpp:1:1: error: broken",
        "/src/foo.cpp:2:1: error: broken",
    ]


def test_extract_error_lines_truncates_and_decodes():
    long_line = b"/src/foo.cpp:1:1: error: " + b"x" * 1000 + b"\xff"

    lines = extract_error_lines([long_line])

    assert len(lines) == 1
    assert len(lines[0]) == MAX_LINE_LENGTH
    assert lines[0].startswith("/src/foo.cpp:1:1: error: xxx")


def test_extract_error_lines_matches_before_truncating():
    path = "/builds/worker/checkouts/gecko/" + "a/" * 240 + "foo.cpp"
    line = f"[task 2026-10-14T13:10:45.004Z] 13:10:45     INFO -  {path}:12:3: error: broken"

    lines = extract_error_lines(["[taskcluster 2026-10-14T13:02:11.310Z] start", line])

    assert len(lines) == 1
    assert len(lines[0]) == MAX_LINE_LENGTH
    assert lines[0] == f"{path}:12:3: error: broken"[:MAX_LINE_LENGTH]


def test_format_error_lines_empty():
    assert format_error_lines([]) == ""
    assert format_error_lines([], collapsible=True) == ""


def test_format_error_lines():
    assert format_error_lines(["first error", "second ```error```"]) == (
        "\n```\nfirst error\nsecond '''error'''\n```\n"
    )


def test_format_error_lines_collapsible():
    assert format_error_lines(["first error"], collapsible=True) == (
        "\n<details>\n<summary>1 error line from the log</summary>\n\n"
        "```\nfirst error\n```\n\n</details>\n"
    )
    assert format_error_lines(["first error", "second error"], collapsible=True) == (
        "\n<details>\n<summary>2 error lines from the log</summary>\n\n"
        "```\nfirst error\nsecond error\n```\n\n</details>\n"
    )
