import re

MAX_ERROR_LINES = 20
MAX_LINE_LENGTH = 500

IN_SEARCH_TERMS = (
    "TEST-UNEXPECTED-",
    "fatal error",
    "FATAL ERROR",
    "Hit MOZ_CRASH",
    "REFTEST ERROR",
    "PROCESS-CRASH",
    "Assertion fail",
    "###!!! ABORT:",
    "SUMMARY: AddressSanitizer",
    "SUMMARY: ThreadSanitizer",
    "SUMMARY: UndefinedBehaviorSanitizer",
    "ThreadSanitizer: nested bug",
    "Automation Error:",
    "command timed out:",
    "wget: unable ",
    "bash.exe: *** ",
    "Unsuccessful task run with exit code: 137",
    "YOU ARE LEAKING THE WORLD",
)

RE_ERR_MATCH = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*"
    r"|^[A-Za-z.]+Error: "
    r"|^[A-Za-z.]*Exception: "
    r"|^\[  FAILED  \] "
    r"|^remoteFailed:"
    r"|^rm: cannot "
    r"|^abort:"
    r"|^\[taskcluster\] Error:"
    r"|^\[[\w._-]+:(?:error|exception)\]"
)

RE_ERR_SEARCH = re.compile(
    r" error\(\d*\):"
    r"|:\d+: error:"
    r"| error R?C\d*:"
    r"|ERROR [45]\d\d:"
    r"|mozmake\.(?:exe|EXE)(?:\[\d+\])?: \*\*\*"
)

RE_EXCLUDE_1_SEARCH = re.compile(
    r"TEST-(?:INFO|PASS) "
    r"|A content process crashed and MOZ_CRASHREPORTER_SHUTDOWN is set, shutting down"
)

RE_EXCLUDE_2_SEARCH = re.compile(
    r"I[ /](Gecko|TestRunner).*TEST-UNEXPECTED-"
    r"|Assertion failure$"
    r"|^TEST-UNEXPECTED-WARNING\b"
    r"|^TimeoutException: "
    r"|^ImportError: No module named pygtk$"
    r"|non-fatal error"
)

RE_ERR_1_MATCH = re.compile(r"^\d+:\d+:\d+ +(?:ERROR|CRITICAL|FATAL) - ")

RE_TASKCLUSTER_NORMAL_PREFIX = re.compile(
    r"^\[(?!taskcluster:)[^\]]*20\d{2}-[^\]]+\]\s"
)

RE_MOZHARNESS_PREFIX = re.compile(r"^\d+:\d+:\d+ +(?:DEBUG|INFO|WARNING) - +")

RE_MOZHARNESS_DISPLAY_PREFIX = re.compile(
    r"^\d+:\d+:\d+ +(?:DEBUG|INFO|WARNING|ERROR|CRITICAL|FATAL) - +"
)

RE_MAKE_ERROR = re.compile(
    r"^g?make(?:\[\d+\])?: \*\*\*|mozmake\.(?:exe|EXE)(?:\[\d+\])?: \*\*\*"
)


def is_error_line(line):
    if RE_EXCLUDE_1_SEARCH.search(line):
        return False

    if RE_ERR_1_MATCH.match(line):
        return True

    trimline = RE_MOZHARNESS_PREFIX.sub("", line).rstrip()
    if RE_EXCLUDE_2_SEARCH.search(trimline):
        return False

    return bool(
        any(term in trimline for term in IN_SEARCH_TERMS)
        or RE_ERR_MATCH.match(trimline)
        or RE_ERR_SEARCH.search(trimline)
    )


def extract_error_lines(lines, max_lines=MAX_ERROR_LINES):
    is_taskcluster = False
    seen = set()
    errors = []

    for line in lines:
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        line = line[:MAX_LINE_LENGTH]

        if line.startswith("[taskcluster "):
            is_taskcluster = True
        if is_taskcluster:
            line = RE_TASKCLUSTER_NORMAL_PREFIX.sub("", line)

        if not is_error_line(line):
            continue

        cleaned = RE_MOZHARNESS_DISPLAY_PREFIX.sub("", line).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            errors.append(cleaned)

    if any(not RE_MAKE_ERROR.search(error) for error in errors):
        errors = [error for error in errors if not RE_MAKE_ERROR.search(error)]

    return errors[:max_lines]


def format_error_lines(lines, collapsible=False):
    if not lines:
        return ""

    block = "```\n{}\n```".format(
        "\n".join(line.replace("```", "'''") for line in lines)
    )

    if not collapsible:
        return f"\n{block}\n"

    summary = f"{len(lines)} error line{'s' if len(lines) > 1 else ''} from the log"
    return f"\n<details>\n<summary>{summary}</summary>\n\n{block}\n\n</details>\n"
