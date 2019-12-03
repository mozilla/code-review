# -*- coding: utf-8 -*-
from taskcluster.helper import TaskclusterConfig

taskcluster_config = TaskclusterConfig("https://firefox-ci-tc.services.mozilla.com")
community_taskcluster_config = TaskclusterConfig(
    "https://community-tc.services.mozilla.com"
)


MONITORING_PERIOD = 7 * 3600

QUEUE_MERCURIAL = "mercurial"
QUEUE_MERCURIAL_APPLIED = "mercurial:applied"
QUEUE_MONITORING = "monitoring"
QUEUE_MONITORING_COMMUNITY = "monitoring:community"
QUEUE_PHABRICATOR_RESULTS = "results"
QUEUE_WEB_BUILDS = "builds"
QUEUE_PULSE_TRY_TASK_END = "pulse:try_task_end"
QUEUE_PULSE_BUGBUG_TEST_SELECT = "pulse:bugbug_test_select"
QUEUE_BUGBUG = "bugbug"
QUEUE_BUGBUG_TRY_PUSH = "bugbug:try_push"
QUEUE_PULSE_AUTOLAND = "pulse:autoland"
