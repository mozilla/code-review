#!/bin/bash -x

git remote add services git@github.com:mozilla/release-services.git
git fetch services

# Add source code
git checkout master
git branch -D import dev
git checkout services/master -b import
git filter-branch -f --prune-empty --subdirectory-filter 'src/staticanalysis' import

# GC
git -c gc.reflogExpire=0 -c gc.reflogExpireUnreachable=0 -c gc.rerereresolved=0 -c gc.rerereunresolved=0 -c gc.pruneExpire=now gc

# On top
git checkout import -b dev

# Remove nix files
find . -name '*.nix' -exec rm {} \;
git commit -a -m 'Remove nix files'

# Fix setup.cfg
rm bot/setup.cfg
git show services/master:nix/setup.cfg > bot/setup.cfg
git commit -a -m 'Import setup.cfg' 

# Add gitignore
echo '*.pyc' > .gitignore
echo '*.egg-info' >> .gitignore
git add .gitignore
git commit -m 'Add .gitignore for python'

# Fix requriements
echo 'flake8' > bot/requirements-dev.txt
echo 'flake8-isort' >> bot/requirements-dev.txt
echo 'pytest' >> bot/requirements-dev.txt
echo 'responses' >> bot/requirements-dev.txt
echo 'pyyaml' >> bot/requirements.txt

# Setup python deps
virtualenv -p /usr/bin/python3 py3-bot
source py3-bot/bin/activate
pip install -r bot/requirements.txt
pip freeze > bot/requirements_frozen.txt
git commit -a -m 'Update Python requirements'

# Add dev tools
pip install -r bot/requirements-dev.txt

# Rename base python module
rm -rf bot/code_review_bot
git mv bot/static_analysis_bot bot/code_review_bot
git commit -m 'Rename static_analysis_bot to code_review_bot'

# Patch imports
import_files=$(git grep -l 'from static_analysis_bot')
sed -i 's/from static_analysis_bot/from code_review_bot/g' $import_files
sed -i 's/static_analysis_bot/code_review_bot/g' bot/setup.py bot/setup.cfg
sed -i 's/static-analysis-bot/code-review-bot/g' bot/README.md bot/code_review_bot/config.py bot/setup.py
sed -i 's/static analysis/code review/g' bot/README.md bot/setup.py
isort $import_files
git commit -a -m 'Fix imports'

# Patch failing unit test
sed -i -e 's,http://taskcluster.test/notify,http://taskcluster.test/api/notify,g' bot/tests/test_reporter_mail.py
git commit -a -m 'Fix unit test'

# Import code from build
files=".taskcluster.yml bot frontend"
git diff $(git rev-list build | tail -n 1)..build -- $files > build.diff
patch -p1 -i build.diff

# Services is not needed anymore
git remote rm services

# Cleanup
#rm -rf py3-bot

# Test
cd bot
pip install -e .
pytest
flake8
