# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import json
import os

import jsone
import jsonschema

with open(os.path.join("VERSION")) as f:
    version = f.read().strip()


def test_jsone_validates(tmp_path):
    payload = {}
    hook_file = os.path.realpath("taskcluster-hook.json")
    assert os.path.exists(hook_file)

    content = open(hook_file).read()
    content = content.replace("CHANNEL", "dev")
    content = content.replace("VERSION", version)

    hook_content = json.loads(content)

    jsonschema.validate(instance=payload, schema=hook_content["triggerSchema"])

    jsone.render(hook_content, context={"payload": payload})
