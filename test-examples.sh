#!/bin/bash
source venv/bin/activate
THREADBARE_TEST_HOST=34.201.187.7 THREADBARE_TEST_USER=elife pytest example.py -vv "$@"
