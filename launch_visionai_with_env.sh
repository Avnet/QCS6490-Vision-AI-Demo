#!/bin/bash

mount -o rw,remount /

# Default to relative path, but allow override via environment variable. Helpful for dev vs prod env
VISIONAI_PATH="${VISIONAI_PATH_OVERRIDE:-./visionai.py}"

# Qprof essentials
export QMONITOR_BACKEND_LIB_PATH=/var/QualcommProfiler/libs/backends/
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/var/QualcommProfiler/libs/
export PATH=$PATH:/data/shared/QualcommProfiler/bins

export XDG_RUNTIME_DIR=/dev/socket/weston
export WAYLAND_DISPLAY=wayland-1

# Prompt user to choose between standard demo or IoTConnect-enabled demo.
# Default after 3 seconds is the standard demo.
echo "Press 'i' within 3 seconds to run the /IOTCONNECT-enabled demo."
echo "Otherwise, the standard visionai.py will run by default."
VISIONAI_PATH=""  # will be set based on user choice below

# Wait up to 3 seconds for a single keypress
if read -t 3 -n 1 key; then
    if [[ "$key" == "i" || "$key" == "I" ]]; then
        VISIONAI_PATH="${VISIONAI_PATH_OVERRIDE:-./visionai-iotc.py}"
        echo "Selected: /IOTCONNECT-enabled demo."
    else
        VISIONAI_PATH="${VISIONAI_PATH_OVERRIDE:-./visionai.py}"
        echo "Selected: standard demo."
    fi
else
    # timed out → default to standard demo
    VISIONAI_PATH="${VISIONAI_PATH_OVERRIDE:-./visionai.py}"
    echo "No input detected. Defaulting to standard demo."
fi

# Execute the chosen demo
exec "$VISIONAI_PATH"