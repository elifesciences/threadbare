#!/bin/bash
# self contained test script intended for CI.
# starts the dummy ssh server and runs ALL tests then kills the dummy ssh server.

set -e

echo "(destroying any venv)"
rm -rf venv/

# creates a venv and test dependencies
. install.sh -dev

./tests-remote/sshd-server.sh &
pid=$!

# it's possible to hit pytest before sshd-server has finished.
# ensure sshd is available before starting tests.
while true; do
    sleep 1
    test -f "/tmp/sshd-dummy/.ssh/dummy_user_key" && break
    echo "waiting for sshd-server to become available ..."
done

echo "pid:$pid"
function finish {
    echo "cleaning up: $pid"
    # terminates the child sshd server that in turn ends the `sshd-server.sh` script
    kill $(pgrep -P "$pid") 
}
trap finish EXIT

# remove any old compiled python files
# pylint likes to lint them, pytest likes to test them
find threadbare/ -name '*.py[c|~]' -delete
find tests/ -name '*.py[c|~]' -delete
find threadbare/ -regex "\(.*__pycache__.*\|*.py[co]\)" -delete
find tests/ -regex "\(.*__pycache__.*\|*.py[co]\)" -delete

export THREADBARE_TEST_PORT=8462
export THREADBARE_TEST_USER="$USER"
export THREADBARE_TEST_PUBKEY="/tmp/sshd-dummy/.ssh/dummy_user_key"

source venv/bin/activate

# no further args passed to test script
# run with coverage and reporting enabled
for transfer_protocol in "scp" "sftp" "rsync"; do
    echo "---------- testing with $transfer_protocol"
    THREADBARE_TEST_TRANSFER_PROTOCOL="$transfer_protocol" PYTHONPATH=threadbare/ \
        python -m pytest \
            example.py tests/ \
            -vv \
            --cov=threadbare/ \
            --cov-report html --cov-report term \
            --cov-fail-under 93
done
