#!/bin/bash

apt-get update
apt-get install --no-install-recommends -y php-cli php-curl curl

curl -L https://github.com/phacility/libphutil/archive/master.tar.gz | tar -C /opt -xvz
mv /opt/libphutil-master /opt/libphutil

curl -L https://github.com/phacility/arcanist/archive/master.tar.gz | tar -C /opt -xvz
mv /opt/arcanist-master /opt/arcanist

apt-get purge -y curl
apt-get autoremove -y
rm -rf /var/lib/apt/lists/*
