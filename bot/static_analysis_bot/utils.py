# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import os
import tempfile
from contextlib import contextmanager


@contextmanager
def build_temp_file(content, suffix):
    '''
    Build a temporary file and remove it after usage
    '''
    assert isinstance(content, str)
    assert isinstance(suffix, str)

    # Write patch in tmp
    _, path = tempfile.mkstemp(suffix=suffix)
    with open(path, 'w') as f:
        f.write(content)

    yield path

    # Cleanup
    os.unlink(path)
