#!/bin/bash
# quick and dirty script for updating requirements-py2.txt

rm -rf venv/
virtualenv2 venv
source venv/bin/activate
pip install wheel pip --upgrade
VIRTUAL_ENV="venv" pipenv sync
pip install pytest pytest-cov mock
VIRTUAL_ENV="venv" pipenv run pip freeze > requirements-py2.txt
