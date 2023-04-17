# Code Review Backend

## Developer setup

### Run the application

You may want to install dependencies in a virtual environment an run the development test server with a base fixure for development purpose:

```
mkvirtualenv -p /usr/bin/python3 code-review-backend
cd backend
pip install -r requirements.txt
./manage.py migrate
./manage.py createsuperuser
./manage.py loaddata fixtures/repositories.json
./manage.py runserver
```

At this point, you can log into http://127.0.0.1:8000/admin/ with the credentials you mentioned during the `createsuperuser` step.

### Debugging tools

Run `pip install -r requirements-dev.txt` to install all the available optional dev tools for the backend.

[Django Debug Toolbar](https://django-debug-toolbar.readthedocs.io/en/latest/) provides you with a neat debug sidebar that will help diagnosing slow API endpoints.

[Django Extensions](https://django-extensions.readthedocs.io/en/latest/) adds a _lot_ of `manage.py` commands ; the most important one is `./manage.py shell_plus` which runs the usual shell but with all the available models pre-imported.

You may also want to use IPython (`pip install ipython`) to get a nicer shell with syntax highlighting, auto reloading and much more via `./manage.py shell`.

## Load existing issues

To load remote issues from production (default configuration):

```
./manage.py load_issues
```

To load already retrieved issues

```
./manage.py load_issues --offline
```

To load from testing

```
./manage.py load_issues --environment=testing
```

## Use a DB dump from testing or production

You can retrieve a Database dump from an Heroku instance on your computer using (process [documented on Heroku](https://devcenter.heroku.com/articles/heroku-postgres-import-export)):

```
heroku pg:backups:capture -a code-review-backend-testing
heroku pg:backups:download -a code-review-backend-testing
```

This will produce a local Postgres binary dump named `latest.dump`.

To use this dump, you'll need a local PostgreSQL instance running. The following Docker configuration works well for local development:

- a `code_review` database is created,
- with user/password credentials `postgres` / `crdev1234`,
- data is stored in a Docker volume named `code_review_postgres`,
- default Postgres port **5432** on the host is mapped to the container.

```
docker run --rm -p 5432:5432 \
  -e POSTGRES_DB=code_review \
  -e POSTGRES_PASSWORD=crdev1234 \
  -v code_review_postgres:/var/lib/postgresql/data \
  postgres
```

To restore the dump, use the following command (using the password used to start the database):

```
pg_restore --verbose --clean --no-acl --no-owner -h localhost -U postgres -d code_review latest.dump
```

It's also possible to use a direct one-step command from Heroku, but you need to have a compatible version of pg_dump on your system (moght be tricky in some scenarios):

```
heroku pg:pull  postgresql-concave-XXX --app code-review-backend-production postgresql://postgres@localhost:5432/prod
```

The postgresql database name can be found through the CLI `pg:info` tool, or on the Heroku dashboard. More information on the [official documentation](https://devcenter.heroku.com/articles/heroku-postgresql#pg-push-and-pg-pull)

Finally you can use that database with the backend as:

```
export DATABASE_URL=postgres://postgres:crdev1234@localhost/code_review
./manage.py runserver
```
