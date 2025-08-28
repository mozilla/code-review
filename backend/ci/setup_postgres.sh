#!/bin/bash -ex
export PG_VERSION=17

# Silent apt
export DEBIAN_FRONTEND=noninteractive

# Install postgresql
apt update
apt install -qq -y postgresql-$PG_VERSION

# Setup access rights
cp $(dirname $0)/pg_hba.conf /etc/postgresql/$PG_VERSION/main/pg_hba.conf

# Start postgresql
pg_ctlcluster $PG_VERSION main start

# Create user & database
su postgres -c 'createuser --createdb tester'
su postgres -c 'createdb --owner=tester code-review'
