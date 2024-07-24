# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

from code_review_bot.report.lando import LANDO_MESSAGE, LandoReporter

MOCK_LANDO_API_URL = "http://api.lando.test"
MOCK_LANDO_TOKEN = "Some Test Token"


class MockLandoWarnings:
    """
    LandoWarnings Mock class
    """

    def __init__(self, api_url, api_key):
        self.api_url = MOCK_LANDO_API_URL
        self.api_key = MOCK_LANDO_TOKEN

    def del_warnings(self, warnings):
        pass

    def add_warning(self, warning, revision_id, diff_id):
        self.revision_id = revision_id
        self.diff_id = diff_id
        self.warning = warning

    def del_all_warnings(self, revision_id, diff_id):
        self.revision_id = revision_id
        self.diff_id = diff_id


def test_lando(log, mock_clang_tidy_issues, mock_revision):
    """
    Test lando reporter
    """

    # empty config should be OK
    assert LandoReporter({}).lando_api is None

    r = LandoReporter({})

    lando_api = MockLandoWarnings(api_url=MOCK_LANDO_API_URL, api_key=MOCK_LANDO_TOKEN)

    r.setup_api(lando_api)

    assert r.lando_api == lando_api

    assert log.has("Publishing warnings to lando is enabled by the bot!")

    r.publish(mock_clang_tidy_issues, mock_revision, [], [], [])

    assert lando_api.revision_id == mock_revision.revision["id"]
    assert lando_api.diff_id == mock_revision.diff_id
    assert lando_api.warning == LANDO_MESSAGE.format(
        errors=1, errors_noun="error", warnings=0, warnings_noun="warnings"
    )

    assert log.has("Publishing warnings to lando for 1 errors and 0 warnings")
