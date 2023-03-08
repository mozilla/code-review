#!/bin/bash -ex
MERCURIAL_VERSION="6.3.3"
VERSION_CONTROL_TOOLS_REV="835df2f1d28a841a8062246dd58c8f41201ff6d3"

apt-get update
apt-get install --no-install-recommends -y curl python-dev gcc openssh-client libjemalloc2

pip install --disable-pip-version-check --quiet --no-cache-dir mercurial==$MERCURIAL_VERSION

# Setup mercurial with needed extensions
hg clone -r $VERSION_CONTROL_TOOLS_REV https://hg.mozilla.org/hgcustom/version-control-tools /src/version-control-tools/
mkdir -p /etc/mercurial/hgrc.d
ln -s /src/tools/docker/hgrc /etc/mercurial/hgrc.d/code-review.rc

# Cleanup
apt-get purge -y gcc curl python-dev
apt-get autoremove -y
rm -rf /var/lib/apt/lists/*
rm -rf /src/version-control-tools/.hg /src/version-control-tools/ansible /src/version-control-tools/docs /src/version-control-tools/testing
