#!/bin/sh
# Script to update b20q. Edit this if your configuration is something other than
# simply a git repo cloned from upstream.
git fetch --all
git reset --hard origin/master
git pull
chmod +x update.sh

