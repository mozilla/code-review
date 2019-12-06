#!/bin/bash -ex
MERCURIAL_VERSION="5.1"

apt-get update
apt-get install --no-install-recommends -y curl python2-minimal python-bz2file python-dev gcc openssh-client

# Setup mercurial from its own website, without install pip2 which has a lot of dependencies
curl -L https://www.mercurial-scm.org/release/mercurial-$MERCURIAL_VERSION.tar.gz | tar -C /opt -xvz
cd /opt/mercurial-$MERCURIAL_VERSION
python2 setup.py install

# Setup mercurial with needed extensions
hg clone -u cc7be0763bb7cb36e64b55b8cec6998741709776 https://hg.mozilla.org/hgcustom/version-control-tools /src/version-control-tools/
mkdir -p /etc/mercurial/hgrc.d

# Cleanup
apt-get purge -y gcc curl python-dev
apt-get autoremove -y
rm -rf /var/lib/apt/lists/*
rm -rf /src/version-control-tools/.hg /src/version-control-tools/ansible /src/version-control-tools/docs /src/version-control-tools/testing
