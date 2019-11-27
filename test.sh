#!/bin/bash
set -e

# remove any old compiled python files
# pylint likes to lint them, pytest likes to test them
find threadbare/ -name '*.py[c|~]' -delete
find tests/ -name '*.py[c|~]' -delete
find threadbare/ -regex "\(.*__pycache__.*\|*.py[co]\)" -delete
find tests/ -regex "\(.*__pycache__.*\|*.py[co]\)" -delete

dev=${1:-""}
if [ "$dev" = "" ]; then
    tox --parallel auto
else
    shift # pop the first arg off
    source venv/bin/activate
    PYTHONPATH=threadbare/ python -m pytest tests/ -vv "$@"
fi
