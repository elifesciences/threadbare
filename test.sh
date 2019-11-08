#!/bin/bash
set -e
source venv/bin/activate
PYTHONPATH=threadbare/ python -m pytest tests/ -vv
