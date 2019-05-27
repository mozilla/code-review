#!/bin/bash -x

git remote add services git@github.com:mozilla/release-services.git
git fetch services

git checkout services/master
git filter-branch --prune-empty --subdirectory-filter 'src/staticanalysis' services/master
