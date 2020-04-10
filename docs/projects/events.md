# Code review Events

This is a Python 3 distributed application, split between a public API endpoint and mercurial workers, all running in the same Heroku application.

The technical information on how to get started is available in the [project README](/events/README.md).

This project is used by the Phabricator Harbormaster build plan: every patch published sends an HTTP request on the public endpoint, which in turns get stored in a shared Redis database, then the build's patch is applied and pushed to Try.

## Deployment

The application is hosted on Heroku (more information in [debugging](/docs/debugging.md) to get access).

It uses currently a single web dyno on each environment:
- https://events.code-review.moz.tools on production
- https://events.code-review.testing.moz.tools on testing

It is deployed with [task-boot](https://github.com/mozilla/task-boot) on every push to `testing` or `production` branch by an administrator.
The application has no state in its docker image, it can restart immediately and reuse the same database.

The worker dynos are slow to start though, as they need to clone the repositories described in the [configuration](/docs/configuration.md). Current boot time is ~ 10 minutes.

## Workflow

Here is a sequence diagram showcasing the main exchanges between relevant parties:
- Phabricator
- the **web** dyno on Heroku
- the shared Redis database on Heroku
- one of the mercurial **workers** on Heroku
- the Try server

![](events.png)
[Diagram source](events.mermaid)

As you can see the workflow is quite complex, relying on several distributed parts. We decided to create an external library [libmozevent](https://github.com/mozilla/libmozevent) to abstract most of the exchanges.

That library hosts all the code relevant to mercurial workers, Phabricator interactions, and use a bus system to communicate between sub systems.
This allows us to have the same code run in a single process in development, but across several distributed instances in testing & production (on Heroku), linked together through a Redis database.

Each subsystem has input and output queues, and just consumes input queues to get new data to work on (whatever that data may be). Once its process is done, it puts in the relevant output queues the results (it's basically a plugin system, split on a network).

A big advantage of that system is that the high level code in this repository is relatively simple, and mainly *plugs* the right subsystems together. It's also easier to create unit tests for each subsystem, as you can interact with their queues.
