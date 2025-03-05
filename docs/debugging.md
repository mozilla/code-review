# Debugging the code review bot

As a maintainer on the code review bot, you will face errors or bad behaviours. There are a lot of moving parts in the projects, some of them are not directly under our control...

## Tools for live environments

### Live logs with papertrail

The 2 _back-end_ projects (bot & backend) all use [papertrail](https://my.papertrailapp.com) to log every Python `logging` call.

The events are organized with a hierarchy so that you can filter:

- `program:code-review` will display all code review logs from all environments
- `program:code-review/production` will display all code review logs from production
- `program:code-review/production/events` will display all code review logs from events in production

To get access to Papertrail, you need to file a bug and ask `:catlee` for permissions to access the `sallt-team` group (see [Bug 1580134](https://bugzilla.mozilla.org/show_bug.cgi?id=1580134)).

### Exceptions with Sentry

Every exception for the 3 _back-end_ projects (bot, backend & events) are logged on the Mozilla sentry instance.

To get access, you need to file a bug requesting access to the `sallt` project on https://sentry.prod.mozaws.net/. The bug should be assigned to cloudops.

Each project has its own dedicated space on Sentry, allowing you to filter and search issues.

You can also configure Sentry to notify you by email on new exceptions.

### Statistics

Mozilla can use the official influxdb platform to process statistics. To get access to the platform, you need to file a bug, requesting access to cloudops.

You'll then get access to the [code review dashboard](https://earthangel-b40313e5.influxcloud.net/d/Tat_-20Wz/code-review?orgId=1) showing the last 2 weeks of statistics from the code review bot.

It's possible to configure alerts on your account when a metric goes under a certain level.

### Heroku

You'll need access to the `mozillacorporation` group on Heroku. Request on Bugzilla to be added in the mozillian group `heroku-members`. You'll then be able to login through SSO on Heroku (detailed and up to date information on [wiki.mozilla.org](https://wiki.mozilla.org/ReleaseEngineering/How_To/Heroku_CLI)).
Once on Heroku, an existing admin for the code-review platform needs to upgrade your rights so you can manage the related applications.

Finally you'll be able to see recent logs for the code review dynos (backend & events). That's helpful if Papertrail has issues.

### Frontend

The code review frontend hosted on https://code-review.moz.tools (production) and https://code-review.testing.moz.tools (testing) offers a pretty good overview of what is going on in the system.

If you do not have a bunch of reviews in a normal week day on the front page under 20 minutes, something is probably going haywire.

The old version using Taskcluster raw data is still available under https://code-review.moz.tools/#/tasks and will list (slowly) all the publication tasks with their ending tasks. Seeing a lot of red is never a good sign.

### Integration test

The repository also hosts an **integration test**. It's a Python script running daily as a Taskcluster hook to check that the whole stack is working.

You can update its hook in Taskcluster, to send you an email once a revision is applied on phabricator-dev.

If the daily revision from the integration test does not show up, it's a good indicator that something is broken.

### Human probes

Also known as "developers will complain". Our customers are great, and some of them rely heavily on the code review bot.
They will tell you if something goes wrong, as the code review bot adds a link to post issues on every comment, and by now they know where to reach the team on Matrix #code-review-bot.

## Is the platform still running ?

Here is a list of troubleshooting steps when you _know_ that something does not work, but don't know yet which part is buggy:

- Check the frontend. As mentioned above, that's the easiest and fastest way to see what's going on in real time
- Check the logs. Start by looking for the Taskcluster hook logs, as that's the first piece that could fail in the workflow.
- If taskcluster analysis tasks are behaving normally, applying revisions, pick a try job from the logs, and follow it
- Check the decision task is creating analyzers and the code-review ending task
- Check the analyzers create some json artifacts, and look for incoherent data in the output. Are the tasks in a coherent status?
- Check the code review hook on firefox-ci: Is it triggered ? Are there bot jobs in papertrail ? Can you find the bot task for the try task you were looking before in the logs ?
- Check the bot execution on the job, through its Taskcluster logs. Check the build updates on Phabricator.
- Check the backend is running, through Papertrail or Heroku logs. Is the postgresql database full ?

## Testing changes

When developing a new feature in the stack, it's primordial to test changes before shipping anything. You especially want to check the output on Phabricator for a known set of issues.

### Running locally on same revision

As a developer on the platform, you must be able to check your code changes locally. Each project has its own way to run, but the bot is the most interesting part as that's the most _public facing_ part.

A simple test is to pick a known try job with a set of issues (you need to know the task group id, and the code-review issues task id). Then you can run the bot before and after your changes with the Phabricator reporter disabled so you do not pollute an existing revision.

```bash
export TRY_TASK_GROUP_ID="xxx"
export TRY_TASK_ID="yyy"
code-review-bot -c code-review-local-dev.yml
```

This small boot script will use a local configuration `code-review-local-dev.yml` (that's where you disable the reporters) aiming at a given task group with issues.

### Using phabricator-dev

You could also configure the setup above to publish on Phabricator dev : https://phabricator-dev.allizom.org

If you create a dummy revision on that instance (creating a bad patch, and publishing it with moz-phab on that Phabricator instance), you will get your own treeherder job, and more importantly your own Phabricator revision on a separate server.

Here is a good example: https://phabricator-dev.allizom.org/D1758

The testing environment is normally configured to publish issues on that Phabricator instance.

### Shadow mode

It's also possible to run the code review testing instance in **shadow mode**.

In that setup, the bot project has phabricator credentials for the production instance, and the Phabricator reporter disabled. It will then be triggered for every patch published in production (so a lot more than on phabricator-dev), without publishing results (or you would pollute every revision with dupes !). You can then analyze the behaviour of the bot through its logs, and its crash rate, using a real flow of patches.
