# Debugging the code review bot

As a maintainer on the code review bot, you will face errors or bad behaviours. There are a lot of moving parts in the projects, some of them are not directly under our control...

## Tools for live environments

### Live logs with papertrail

The 3 *back-end* projects (bot, backend & events) all use [papertrail](https://my.papertrailapp.com) to log every Python `logging` calls.

The events are organized with a hierarchy so that you can filter:

- `program:code-review` will display all code review logs from all environment
- `program:code-review/production` will display all code review logs from production
- `program:code-review/production/events` will display all code review logs from events in production

To get access to Papertrail, you need to file a bug and ask `:catlee` for permissions to access the `sallt-team` group (see [Bug 1580134](https://bugzilla.mozilla.org/show_bug.cgi?id=1580134)).

### Exceptions with Sentry

Every exception for the 3 *back-end* projects (bot, backend & events) are logged on the Mozilla sentry instance.

To get access, you need to file a bug requesting access to the `sallt` project on https://sentry.prod.mozaws.net/ The bug should be assigned to cloudops.

Each project has its own dedicated space on Sentry, allowing you to filter and search issues.

You can also configure Sentry to notify you by email on new exceptions.

### Statistics

Mozilla can use the official influxdb platform to process statistics. To get access to the platform, you need to file a bug, requesting access to cloudops.

You'll then get access to the [code review dashboard](https://earthangel-b40313e5.influxcloud.net/d/Tat_-20Wz/code-review?orgId=1) showing the last 2 weeks of statistics from the code review bot.

It's possible to configure alerts on your account when a metric goes under a certain level.

### Frontend

The code review frontend hosted on https://code-review.moz.tools (production) and https://code-review.testing.moz.tools (testing) offer a pretty good overview of what is going on in the system.

If you do not have a bunch of reviews in a normal week day on the front page under 20 minutes, something is probably going haywire.

The old version using Taskcluster raw data is still available under https://code-review.moz.tools/#/tasks and will list (slowly) all the publication tasks with their ending tasks. Seeing a lot of red is never a good sign.


### Human probes

Also known as "developers will complain". Our customers are great, and some of them rely heavily on the code review bot.
They will tell you if something goes wrong, as the code review bot adds a link to post issues on every comment, and by now they know where to reach the team on Matrix #code-review-bot.

## Is the platform still running ?

check the frontend

check the logs

start from the beginning

## Testing changes

shadow mode



### Running locally on same revision
