#!/bin/bash
set -e

source venv/bin/activate

# remove any old compiled python files
# pylint likes to lint them, pytest likes to test them
find threadbare/ -name '*.py[c|~]' -delete
find tests/ -name '*.py[c|~]' -delete
find threadbare/ -regex "\(.*__pycache__.*\|*.py[co]\)" -delete
find tests/ -regex "\(.*__pycache__.*\|*.py[co]\)" -delete

pyflakes example.py threadbare/ tests/
black example.py threadbare/ tests/ --target-version py27
