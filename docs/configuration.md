# Configuration

The whole project uses [Taskcluster secrets](https://docs.taskcluster.net/docs/manual/using/secrets) as a source of configuration.
We use a shared secret amongst every actor of the system, with a hierarchy so that common configurations can be easily shared without duplication.

The source code to manage secrets is in the [Taskcluster python library](https://github.com/taskcluster/taskcluster/blob/master/clients/client-py/taskcluster/helper.py) itself.

A developer can also specify its local configuration using a YAML file, with the same exact structure as the secret described below.

We use one secret per environment, on the firefox-ci Taskcluster instance:

- `project/relman/code-review/runtime-testing` for the testing environment
- `project/relman/code-review/runtime-production` for the production environment

## Sample commented file

```yaml
# Configuration under the `common` key is shared across the 3 other Python projects (bot, backend & events)
common:
  # This defines the environment name, used to customize logging, reporting, ...
  # Usual choices are: `testing`, `production` or `localdev`, `dev`
  APP_CHANNEL: testing

  # This section defines the optional statistics connection for an InfluxDB database.
  # This system is used and deployed by Mozilla Cloudops team.
  # Of course, it must be disabled on local configurations.
  influxdb:
    ssl: true
    password: xxxx
    username: yyyy
    database: zzzz
    port: 8086
    host: something.influxcloud.net

  # These two keys allow the project to log everything on Papertrail, so that administrators can troubleshoot the system.
  # For more information, see the debugging documentation.
  # Of course, it must be disabled on local configurations.
  PAPERTRAIL_HOST: logs.papertrailapp.com
  PAPERTRAIL_PORT: 12345

  # A common Phabricator account is shared across the bot and events projects
  # Issues will be published with this account
  # This section is required in local configuration
  PHABRICATOR:
    url: "https://phabricator.services.mozilla.com/api/"
    api_key: api-xxxx
    publish: true

  repositories:
    # A unique display name for the repository
    - name: mozilla-central

      # The repository base url, used to clone the repository
      # and reference it in the backend
      url: "https://hg.mozilla.org/mozilla-central"

      # Try server configuration
      # try_url is the ssh connection string to push patches
      try_url: "ssh://hg.mozilla.org/try"

      # try_name is a display name for that repository
      try_name: try

      # Mercurial checkout mode, several modes available:
      # - robust, to use robustcheckout extension (recommended)
      # - batch, to clone from revision 1 up to tip (slow but lower memory usage)
      # - default, to use the default hg clone (for small repositories only)
      checkout: robust

      # Prefix of the environment variables used by the bot to detect which repository
      # is setup from a decision task (more details on the bot documentation)
      decision_env_prefix: GECKO

      # The ssh username (or email) used to push on Try
      ssh_user: someone@mozilla.com

      # (Optional) private ssh-key overriding the default one setup in the events main section
      ssh_key: xxxx

      # (Optional) Force the application of the patches on top of the repository tip
      # instead of the base revision specified by Phabricator
      use_latest_revision: true

# This main section is only used by the bot project
bot:
  # The list of reporter classes used to publish issues
  REPORTERS:
    # The most important one being Phabricator publication
    # You just need to add that line to use the shared phabricator credentials
    # Every issues deemed publishable will then be posted on the revision
    - reporter: phabricator

    # A debugging tool to receive an email on *every* build processed
    # with the full list of issues
    # Internal use only !
    - reporter: mail
      emails:
        - admin@mozilla.com

    # This reporter will send an extra email to the developers when a build error
    # is detected amongst the issues
    - reporter: build_error

  # Boolean option to enable/disable the low coverage warning
  ZERO_COVERAGE_ENABLED: true

  # Float ratio (between 0.0 and 1.0) defining the chance for a patch to be analyzed with
  # the before/after feature (filters out known issues and warn about issues outside the patch)
  BEFORE_AFTER_RATIO: 0.3

  # Connection information to publish issues on the backend
  # On local development it should be set to the local backend running in Docker
  backend:
    url: "https://api.code-review.moz.tools"

    # That user can be created through the administration interface
    username: xxxx
    password: yyy

  # Sentry connection string to publish system exceptions
  # Each project has its own Sentry environment
  SENTRY_DSN: https://xxx:yyy@sentry.com

# This main section is only used by the backend project
# Note: The postgresql connection string is provided by Heroku as an environment variable
backend:
  # Configure a list of allowed domains through CORS
  # Useful for another frontend to use data from that backend
  # Like on the Taskcluster builds
  cors-domains:
    - "https://community.taskcluster-artifacts.net"

  # Sentry connection string to publish system exceptions
  # Each project has its own Sentry environment
  SENTRY_DSN: https://xxx:yyy@sentry.com

# This main section is only used by the events project
# Note: The redis connection string is provided by Heroku as an environment variable
events:
  # Sentry connection string to publish system exceptions
  # Each project has its own Sentry environment
  SENTRY_DSN: https://xxx:yyy@sentry.com

  # Does the system need to listen for autoland or mozilla-central payloads on pulse
  # This is needed to ingest issues in the backend
  autoland_enabled: true
  mozilla_central_enabled: true

  # Pulse authentication to get messages for the autoland and mozilla-central triggers
  pulse_user: xxx
  pulse_password: yyy

  # Parameters for the test selection feature
  # TODO: Marco may document a bit more here
  bugbug_phabricator_deployment: dev
  test_selection_enabled: false
  test_selection_share: 0.03
  test_selection_notify_addresses:
    - admin@mozilla.com

  # Skip all revisions produced by these users
  # It's useful to avoid huge revisions produced by bots
  user_blacklist:
    - bot-username-a
    - bot-username-b

  # Taskcluster credentials for the community instance
  # Needed to run the bugbug analysis
  taskcluster_community:
    client_id: project/relman/bugbug/xxxx
    access_token: yyy

  # Pulse authentication on the community Taskcluster instance
  # to get messages for the test selection triggers
  communitytc_pulse_user: xxxx
  communitytc_pulse_password: yyy

  # Phabricator usernames for whom a risk analysis will be triggered
  # when they are authors or reviewers of a patch
  risk_analysis_users:
    - user-a
    - user-b

  # The SSH private key used to push patches on the Try server
  # It can be setup globally for the events project, or specified per repository
  ssh_key: |-
    -----BEGIN RSA PRIVATE KEY-----
    SomePrivateKeyHere
    -----END RSA PRIVATE KEY-----
```
