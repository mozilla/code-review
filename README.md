# Mozilla Code Review

The **Code Review Bot** aims to give early feedback to Mozilla developers about their patches. We automate code analyzers and publish detected issues on Phabricator as soon as possible, and for all revisions.

This project has 5 parts:

* `bot` is a Python 3 script running as a Taskcluster task, reporting issues found in analyzer tasks,
* `backend` is a Django web API used to store issues detected by the bot,
* `frontend` is an administration frontend (in Vue.js) displaying detailed information about analyses and issues,
* `events` is a Python 3 distributed application running in Heroku that receives Phabricator notifications and triggers Try pushes,
* `integration` is a Python 3 script running daily as a Taskcluster hook to check that the whole stack is working.

:blue_book: Documentation is available in this repository [in the docs folder](docs/README.md). A good starting point is the [architecture description](docs/architecture.md).

:loudspeaker: You can contact the code review bot's developers [on Matrix](https://chat.mozilla.org/#/room/#code-review-bot:mozilla.org) or on Slack in #code-review-bot.
