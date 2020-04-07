#!/bin/bash

. mkvenv.sh

source venv/bin/activate
pip install -r requirements.txt

if [ -e venv/bin/python2.7 ]; then
    pip install -r requirements-py2.txt
fi
