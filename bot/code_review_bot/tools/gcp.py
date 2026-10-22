# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import json

from google.cloud import secretmanager
from google.oauth2 import service_account


def access_secret_with_keyfile(secret_name, keyfile_content):
    """
    Read a secret from GCP Secret Manager using a service account keyfile.
    The secret name must be a full version resource name, i.e.
    projects/<project>/secrets/<secret>/versions/<version>
    """
    if isinstance(keyfile_content, str):
        account_info = json.loads(keyfile_content)
    else:
        account_info = keyfile_content

    credentials = service_account.Credentials.from_service_account_info(account_info)
    client = secretmanager.SecretManagerServiceClient(credentials=credentials)
    response = client.access_secret_version(request={"name": secret_name})

    return response.payload.data.decode("UTF-8")
