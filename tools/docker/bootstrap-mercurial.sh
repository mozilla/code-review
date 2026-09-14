#!/bin/bash -ex
MERCURIAL_VERSION="7.2.2"
VERSION_CONTROL_TOOLS_REV="6bf453c1aecd9bd8934a4c8a2b0d9a299bf96e17"

# Check source hgrc is available
HGRC=/src/tools/docker/hgrc
if [[ ! -f $HGRC ]]; then
	echo "Missing hgrc in $HGRC"
	exit 1
fi

apt-get update
apt-get install --no-install-recommends -y curl python-dev-is-python3 gcc openssh-client libjemalloc2 git

pip install --disable-pip-version-check --quiet --no-cache-dir mercurial==$MERCURIAL_VERSION

# Setup mercurial with needed extensions
hg clone -r $VERSION_CONTROL_TOOLS_REV https://hg.mozilla.org/hgcustom/version-control-tools /src/version-control-tools/
mkdir -p /etc/mercurial/hgrc.d
ln -s $HGRC /etc/mercurial/hgrc.d/code-review.rc

# Cleanup
apt-get purge -y gcc curl python-dev-is-python3
apt-get autoremove -y
rm -rf /var/lib/apt/lists/*
rm -rf /src/version-control-tools/.hg /src/version-control-tools/ansible /src/version-control-tools/docs /src/version-control-tools/testing
