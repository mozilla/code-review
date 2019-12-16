# Code Review Backend

## Developer setup

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

* a `code_review` database is created,
* with user/password credentials `postgres` / `crdev1234`,
* data is stored in a Docker volume named `code_review_postgres`,
* default Postgres port **5432** on the host is mapped to the container.

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

Finally you can use that database with the backend as:

```
export DATABASE_URL=postgres://postgres:crdev1234@localhost/code_review
./manage.py runserver
```
