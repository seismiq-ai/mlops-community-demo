#!/bin/bash

set -e

LAYER_NAME=$1
PYTHON_VERSION=3.12
DIRECTORY="$(pwd)"
LAYER_DIR="$DIRECTORY/layers/$LAYER_NAME"
VENV_DIR="$DIRECTORY/venv_$LAYER_NAME"

# Ensure a fresh layers directory exists
rm -rf "$LAYER_DIR"
mkdir -p "$LAYER_DIR/python/lib/python${PYTHON_VERSION}/site-packages"

# Create and activate a virtual environment
python${PYTHON_VERSION} -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"
# Install dependencies
pip install --upgrade pip
pip install --no-cache-dir --platform manylinux2014_x86_64 --only-binary=:all: -r "requirements.${LAYER_NAME}.txt" -t "${LAYER_DIR}/python/lib/python${PYTHON_VERSION}/site-packages/"

# Create zip file
cd "${LAYER_DIR}"
zip -r "${LAYER_NAME}_layer.zip" python \
    -x '**/__pycache__/*' \
    -x '**/tests/*' \
    -x '**/test/*' \
    -x '**/examples/*' \
    -x '**/docs/*' \
    -x '**/*.pyc' \
    -x '**/*.pyo' \
    -x '**/*.pyd' \
    -x '**/*.egg-info/*'

# Move zip file to the correct location
# mv "${LAYER_NAME}_layer.zip" "${DIRECTORY}/layers/${LAYER_NAME}/"

# Deactivate and remove the virtual environment
deactivate
rm -rf "$VENV_DIR"

# Update permissions of the layer directory
chmod -R 755 "$LAYER_DIR"

echo "Layer created: $LAYER_DIR/${LAYER_NAME}_layer.zip"