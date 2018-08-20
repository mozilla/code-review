Static Analysis
===============

Configuration
-------------

As every other services in `mozilla-releng/services`, the static analysis bot is configured through the [Taskcluster secrets service](https://tools.taskcluster.net/secrets)

The following configuration variables are currently supported:

* `APP_CHANNEL` **[required]** is provided by the common configuration (staging or production)
* `REPORTERS` **[required]** lists all the reporting tools to use when a static analysis is completed (details below)
* `ANALYZERS` **[required]** lists all the analysis tool to run on specified revisions. These tools will produce the reported issues.
* `PAPERTRAIL_HOST` is the optional Papertrail host configuration, used for logging.
* `PAPERTRAIL_PORT` is the optional Papertrail port configuration, used for logging.
* `SENTRY_DSN` is the optional Sentry full url to report runtime errors.
* `MOZDEF` is the optional MozDef log destination.

The `REPORTERS` configuratin is a list of dictionaries describing which reporting tool to use at the end of the patches static analysis.
Supported reporting tools are emails (for admins), MozReview and Phabricator.

Each reporter configuration must contain a `reporter` key with a unique name per tool. Each tool has its own configuration requirement.

Reporter: Mail
--------------

Key `reporter` is `mail`

The emails are sent through Taskcluster notify service, the hook must have `notify:email:*` in its scopes (enabled on our staging & production instances)

Only one configuration is required: `emails` is a list of emails addresses receiving the admin output for each analysis.

This reporter will send detailed informations about every issue.

Reporter: MozReview
-------------------

Key `reporter` is `mozreview`

Configuration:

 * `url` : The Mozreview api url
 * `username` : The Mozreview account's username
 * `api_key` : The Mozreview account's api key 
 * `analyzers` : Limit the reported issues to those produced by specified analyzers. Choices are: `clang-tidy`, `clang-format`, `mozlint`.
 * `publish_success` : a boolean describing if a successfull analysis must be reported (disabled by default)


Reporter: Phabricator
---------------------

Key `reporter` is `phabricator`

Configuration:

 * `url` : The Phabricator api url
 * `api_key` : The Phabricator account's api key 

This reporter will send detailed informations about every **publishable** issue.

Analyzer: Clang Tidy
--------------------

Key is `clang-tidy`

Detect static analysis issues on C/C++ code

Analyzer: Clang Format
--------------------

Key is `clang-format`

Detect linting issues on C/C++ code

Analyzer: MozLint
-----------------

Key is `mozlint`

Detect linting issues on Python and Javascript code

Example configuration
---------------------

```json
{
  "common": {
    "APP_CHANNEL": "staging",
    "PAPERTRAIL_HOST": "XXXX.papertrail.net",
    "PAPERTRAIL_PORT": 12345
  },
  "static-analysis-bot": {
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
        "url": "https://dev.phabricator.mozilla.com",
        "api_key": "deadbeef123456"
      },
      {
        "reporter": "mozreview",
        "url": "https://reviewboard.mozilla.org",
        "api_key": "coffee123456",
        "username": "sa-bot-staging",
        "analyzers": ["clang-tidy", "clang-format", "mozlint"]
      }
    ],
    "ANALYZERS": [
      "clang-tidy",
      "clang-format",
      "mozlint"
    ]
  }
}
```
