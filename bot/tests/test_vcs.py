# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from code_review_bot import vcs
from code_review_bot.config import settings


def test_bugbug_default_configuration():
    """
    The shipped rollout configuration is usable: a percentage expressed as a
    ratio, a non empty allow list and a non empty optimize strategy
    """
    assert 0 <= settings.bugbug_enabled_percent <= 1
    assert settings.bugbug_enabled_repositories
    assert settings.bugbug_optimize_strategy


def test_bugbug_disabled_for_unlisted_repository(monkeypatch):
    """
    Repositories outside of the allow list are never selected, even when the
    rollout percentage is at its maximum
    """
    monkeypatch.setattr(settings, "bugbug_enabled_percent", 1)

    assert vcs.bugbug_enabled("mozilla-central") is False
    assert vcs.bugbug_enabled("nss") is False


def test_bugbug_enabled_for_listed_repository(monkeypatch):
    """
    Repositories from the allow list are selected by the rollout percentage
    """
    monkeypatch.setattr(settings, "bugbug_enabled_repositories", ["autoland"])

    monkeypatch.setattr(settings, "bugbug_enabled_percent", 1)
    assert vcs.bugbug_enabled("autoland") is True

    monkeypatch.setattr(settings, "bugbug_enabled_percent", 0)
    assert vcs.bugbug_enabled("autoland") is False
