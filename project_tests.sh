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
PYTHONPATH=threadbare/ python -m pytest \
    example.py tests/ \
    -vv \
    --cov=threadbare/ \
    --cov-report html --cov-report term \
    --cov-fail-under 95
