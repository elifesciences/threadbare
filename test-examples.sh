#!/bin/bash
set -e

# check the dummy ssh server is running on port 2222
# see ./tests-remote/sshd-server.sh
# and ./tests-remote/ssh-client.sh
die=false
exec 6<>/dev/tcp/localhost/2222 || { 
    die=true
}

if $die; then
    printf "\ndummy ssh server not available. dying.\n"
    exec 6>&- # close output connection
    exec 6<&- # close input connection
    exit 1
fi

export THREADBARE_TEST_HOST=localhost
export THREADBARE_TEST_PORT=2222
export THREADBARE_TEST_USER="$USER"
export THREADBARE_TEST_PUBKEY="$PWD/tests-remote/cert/dummy_user_key"
source venv/bin/activate
pytest example.py -vv "$@"
