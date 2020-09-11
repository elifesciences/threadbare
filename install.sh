#!/bin/bash

env=${1:-} # "-dev" or nothing

. mkvenv.sh

source venv/bin/activate

if [ -e venv/bin/python2.7 ]; then
    pip install -r "requirements-py2.txt"
else
    pip install -r "requirements$env.txt"
fi
