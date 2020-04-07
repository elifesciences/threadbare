#!/bin/bash
set -e

temp_dir="/tmp/sshd-dummy"

# check the dummy ssh server is running on port 2222
# see ./tests-remote/sshd-server.sh
# and ./tests-remote/ssh-client.sh
echo "---------------"
echo "looking for dummy ssh server"
die=false
exec 6<>/dev/tcp/localhost/8462 || {
    die=true
}

if $die; then
    echo "not found, dying."
    echo "---------------"
    exec 6>&- # close output connection
    exec 6<&- # close input connection
    exit 1
fi

echo "found."
echo "---------------"

export THREADBARE_TEST_PORT=8462
export THREADBARE_TEST_USER="$USER"
export THREADBARE_TEST_PUBKEY="$temp_dir/.ssh/dummy_user_key"
source venv/bin/activate
pytest example.py -vv "$@"
