#!/bin/bash
# assumes dev installation

set -e

source venv/bin/activate
pdoc --html --output-dir ./docs --force ./threadbare
