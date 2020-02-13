#!/bin/bash
# assumes dev installation

set -e

source venv/bin/activate
pdoc --html --template-dir ./docs-templates/ --output-dir ./docs --force ./threadbare
mv ./docs/threadbare/* docs/
rmdir ./docs/threadbare/
