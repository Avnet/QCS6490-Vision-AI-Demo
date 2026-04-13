#!/bin/bash

mount -o rw,remount /

# Default to relative path, but allow override via environment variable. Helpful for dev vs prod env
VISIONAI_PATH="${VISIONAI_PATH_OVERRIDE:-./visionai.py}"

# Qprof essentials
export QMONITOR_BACKEND_LIB_PATH=/var/QualcommProfiler/libs/backends/
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/var/QualcommProfiler/libs/
export PATH=$PATH:/data/shared/QualcommProfiler/bins

export XDG_RUNTIME_DIR=/run/user/0

exec "$VISIONAI_PATH"
