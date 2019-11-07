Static Analysis Bot
===================

Developer setup
---------------

The code review bot is a Python 3 application, so it should be easy to bootstrap on your computer:

```
mkvirtualenv -p /usr/bin/python3 code-review
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .
```

You should now be able to run linting and unit tests:

```
flake8
pytest
```

If those tests are OK, you can run the bot locally, by specifying a Taskcluster secret with your configuration, and a task reference to analyze.

```
export TRY_TASK_ID=XXX
export TRY_TASK_GROUP_ID=XXX
code-review-bot --taskcluster-secret=path/to/secret
```

Configuration
-------------

The code review bot is configured through the [Taskcluster secrets service](https://community-tc.services.mozilla.com/secrets)

The following configuration variables are currently supported:

* `APP_CHANNEL` **[required]** is provided by the common configuration (staging or production)
* `REPORTERS` **[required]** lists all the reporting tools to use when a code review is completed (details below)
* `PHABRICATOR` **[required]** holds the credentials to make API calls on Phabricator.
* `ZERO_COVERAGE_ENABLED` is a boolean value enabling or disabling the zero coverage warning report.
* `PAPERTRAIL_HOST` is the optional Papertrail host configuration, used for logging.
* `PAPERTRAIL_PORT` is the optional Papertrail port configuration, used for logging.
* `SENTRY_DSN` is the optional Sentry full url to report runtime errors.

The `REPORTERS` configuration is a list of dictionaries describing which reporting tool to use at the end of the patches code review.
Supported reporting tools are emails (for admins) and Phabricator.

Each reporter configuration must contain a `reporter` key with a unique name per tool. Each tool has its own configuration requirement.

Phabricator credentials
-----------------------

They are required, and must be set like this:

```
  PHABRICATOR:
    url: 'https://phabricator.services.mozilla.com/api/'
    api_key: api-XXXX
```

Reporter: Mail
--------------

Key `reporter` is `mail`

The emails are sent through Taskcluster notify service, the hook must have `notify:email:*` in its scopes (enabled on our staging & production instances)

Only one configuration is required: `emails` is a list of emails addresses receiving the admin output for each analysis.

This reporter will send detailed information about every issue.

Reporter: Phabricator
---------------------

Key `reporter` is `phabricator`

Configuration:

 * `analyzers` : The analyzers that will be published on Phabricator. Possible values are: mozlint, clang-tidy, clang-format, coverity, infer, coverage.

This reporter will send detailed information about every **publishable** issue.

Example configuration
---------------------

```json
{
  "common": {
    "APP_CHANNEL": "staging",
    "PAPERTRAIL_HOST": "XXXX.papertrail.net",
    "PAPERTRAIL_PORT": 12345,
    "PHABRICATOR": {
      "url": "https://dev.phabricator.mozilla.com",
      "api_key": "deadbeef123456"
    }
  },
  "code-review-bot": {
    "REPORTERS": [
      {
        "reporter": "mail",
        "emails": [
          "xxx@mozilla.com",
          "yyy@mozilla.com"
        ]
      },
      {
        "reporter": "phabricator",
        "analyzers": ["clang-tidy", "mozlint"]
      }
    ]
  }
}
```
