#!/bin/bash
set -e

env=${1:-""} # "-dev" or nothing

. mkvenv.sh

source venv/bin/activate
pip install pip wheel --upgrade
pip install -r "requirements$env.txt"
