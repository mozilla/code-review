import json
import time
from contextlib import contextmanager
from pathlib import Path


class ProfilerFile:
    """
    Build a file compatible with profiler.firefox.com
    """

    def __init__(self, path: Path):
        assert isinstance(path, Path)
        self.path = path

    @contextmanager
    def record(self, name):
        """
        Log an event, automatically registering start and end timestamps
        """
        start = time.monotonic()

        # Let the calling code runs
        yield

        end = time.monotonic()

        # 2 is the "Tasks" category.
        record = [
            "marker",
            "code-review-bot",
            start,
            end,
            {"type": "Text", "text": name},
            2,
        ]

        # Immediately append the line to file
        with self.path.open("a+") as f:
            f.write(json.dumps(record) + "\n")
