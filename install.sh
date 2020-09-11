#!/bin/bash

env=${1:-} # "-dev" or nothing

. mkvenv.sh

source venv/bin/activate
pip install -r "requirements$env.txt"

if [ -e venv/bin/python2.7 ]; then
    # requirements-py2.txt
    # requirements-dev-py2.txt
    pip install -r "requirements$env-py2.txt"
fi
