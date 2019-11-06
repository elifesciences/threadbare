#!/bin/bash
set -e
PYTHONPATH=threadbare/ python -m pytest tests/ -v
