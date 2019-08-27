# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import setuptools


def read_requirements(file_):
    lines = []
    with open(file_) as f:
        for line in f.readlines():
            line = line.strip()
            if (
                line.startswith("-e ")
                or line.startswith("http://")
                or line.startswith("https://")
            ):
                extras = ""
                if "[" in line:
                    extras = "[" + line.split("[")[1].split("]")[0] + "]"
                line = line.split("#")[1].split("egg=")[1] + extras
            elif line == "" or line.startswith("#") or line.startswith("-"):
                continue
            line = line.split("#")[0].strip()
            lines.append(line)
    return sorted(list(set(lines)))


with open("VERSION") as f:
    VERSION = f.read().strip()


setuptools.setup(
    name="code_review_events",
    version=VERSION,
    description="Create try jobs for the code review workflow",
    author="Mozilla Release Management",
    author_email="release-mgmt-analysis@mozilla.com",
    url="https://github.com/mozilla/code-review",
    tests_require=read_requirements("requirements-dev.txt"),
    install_requires=read_requirements("requirements.txt"),
    packages=setuptools.find_packages(),
    include_package_data=True,
    zip_safe=False,
    license="MPL2",
    entry_points={
        "console_scripts": ["code-review-events = code_review_events.cli:main"]
    },
)
