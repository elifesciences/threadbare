#!/bin/bash
set -e

# temporary directory where the sshd pid file will be kept. destroyed on entry and exit
temp_dir="/tmp/sshd-dummy/"
rm -rf "$temp_dir"
mkdir -p "$temp_dir"
mkdir "$temp_dir/.ssh"

# allow the dummy user to login to the dummy server
# TODO: generate these files on each run
cat "$PWD/cert/dummy_user_key.pub" > "$temp_dir/.ssh/authorized_keys"

# permissions checking has been disabled in sshd_config
# see `StrictModes`

# -D -- do NOT become a daemon
# -e -- write debug log to stderr
# -h -- host key file, just a simple private key
# -f -- path to further sshd config
# for more output, set "LogLevel DEBUG" in `sshd_config`. default is INFO
/usr/bin/sshd -D -e -f ./sshd_config -h "$PWD/cert/dummy_host_key"

# at this point you can run the ./ssh-client.sh script to check the server is running properly

# clean up
rm -rf "$temp_dir"
