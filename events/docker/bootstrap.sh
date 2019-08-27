#!/bin/bash -ex
MERCURIAL_VERSION="5.1"

apt-get update
apt-get install --no-install-recommends -y curl python2-minimal python-bz2file python-dev

# Setup mercurial from its own website, without install pip2 which has a lot of dependencies
curl -L https://www.mercurial-scm.org/release/mercurial-$MERCURIAL_VERSION.tar.gz | tar -C /opt -xvz
cd /opt/mercurial-$MERCURIAL_VERSION
python2 setup.py install

# Setup mercurial with needed extensions
hg clone https://hg.mozilla.org/hgcustom/version-control-tools /src/version-control-tools/
ln -s /src/docker/hgrc $HOME/.hgrc

# Cleanup
apt-get autoremove -y
rm -rf /src/version-control-tools/.hg
