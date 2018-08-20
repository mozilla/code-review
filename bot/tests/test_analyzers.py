# -*- coding: utf-8 -*-
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import shutil
import subprocess


def test_shellcheck():
    '''
    Test the shellcheck version used
    '''
    path = shutil.which('shellcheck')
    assert path.startswith('/nix/store')

    output = subprocess.check_output(['shellcheck', '--version'])
    assert b'version: 0.4.7' in output
