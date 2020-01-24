#!/bin/bash
set -e

temp_dir="/tmp/sshd-dummy"

if [ ! -e "$key_path" ]; then
    echo "a dummy private key does not exist."
    echo "run ./sshd-server.sh first"
    exit 1
fi

# IdentitiesOnly + IdentityFile -- prevent ssh client from iterating through all possible keys
# StrictHostKeyChecking=no -- do not prompt to accept host's public key
# UserKnownHostsFile=/dev/null -- do not read or write the known_hosts file
# LogLevel=ERROR -- hide the `Warning: Permanently added ... to the list of known hosts.` warning

# for more output use `-v`
ssh \
    -o UserKnownHostsFile=/dev/null \
    -o StrictHostKeyChecking=no \
    -o IdentitiesOnly=yes \
    -o IdentityFile="$temp_dir/.ssh/dummy_user_key" \
    -o LogLevel=ERROR \
    "$USER"@localhost -p 2222 \
    "echo 'success!'"
