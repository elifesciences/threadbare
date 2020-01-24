#!/bin/bash
# self contained test script intended for CI.
# starts the dummy ssh server and runs ALL tests then kills the dummy ssh server.

set -e

rm -rf venv/

. mkvenv.sh

. install.sh

./tests-remote/sshd-server.sh &
pid=$!

# remove any old compiled python files
# pylint likes to lint them, pytest likes to test them
find threadbare/ -name '*.py[c|~]' -delete
find tests/ -name '*.py[c|~]' -delete
find threadbare/ -regex "\(.*__pycache__.*\|*.py[co]\)" -delete
find tests/ -regex "\(.*__pycache__.*\|*.py[co]\)" -delete

export THREADBARE_TEST_HOST=localhost
export THREADBARE_TEST_PORT=2222
export THREADBARE_TEST_USER="$USER"
export THREADBARE_TEST_PUBKEY="/tmp/sshd-dummy/.ssh/dummy_user_key"

# no further args passed to test script
# run with coverage and reporting enabled
PYTHONPATH=threadbare/ python -m pytest \
    example.py tests/ \
    -vv \
    --cov=threadbare/ \
    --cov-report html --cov-report term \
    --cov-fail-under 95

kill "$pid"
