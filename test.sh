#!/bin/bash
set -e

# remove any old compiled python files
# pylint likes to lint them, pytest likes to test them
find threadbare/ -name '*.py[c|~]' -delete
find tests/ -name '*.py[c|~]' -delete
find threadbare/ -regex "\(.*__pycache__.*\|*.py[co]\)" -delete
find tests/ -regex "\(.*__pycache__.*\|*.py[co]\)" -delete

dev=${1:-""}
if [ "$dev" = "dev" ]; then
    shift # pop the first arg off
    source venv/bin/activate
    if [ -z "$@" ]; then
        # no further args passed to test script
        # run with coverage and reporting enabled
        PYTHONPATH=threadbare/ python -m pytest \
            tests/ \
            -vv \
            --cov=threadbare/ \
            --cov-report html --cov-report term \
            --cov-fail-under 75
    else
        # running tests adhoc, skip coverage reporting
        PYTHONPATH=threadbare/ python -m pytest \
            -vv \
            "$@"
    fi
else
    tox --parallel auto "$@"
fi
