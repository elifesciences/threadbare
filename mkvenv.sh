#!/bin/bash
set -e

python=''
pybinlist=("python3.8" "python3" "python2.7")

for pybin in ${pybinlist[*]}; do
    which "$pybin" &> /dev/null || continue
    python=$pybin
    break
done

if [ -z "$python" ]; then
    echo "no usable python found, exiting"
    exit 1
fi

if [ ! -e "venv/bin/$python" ]; then
    echo "could not find venv/bin/$python, recreating venv"
    rm -rf venv
    if [ "$python" = "python2.7" ]; then
        virtualenv2 venv
    else
        $python -m venv venv
    fi
else
    echo "using $python"
fi

source venv/bin/activate
pip install pip wheel --upgrade
