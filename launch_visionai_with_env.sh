#!/bin/bash

mount -o rw,remount /

# Define cleanup function to restore logging
cleanup() {
    echo "Restoring logging services..."
    dmesg -n 7

    # 1. Stop services to ensure handles are released
    for srv in rsyslog syslog-ng syslog busybox-syslogd; do
        systemctl stop "$srv" 2>/dev/null
        /etc/init.d/"$srv" stop 2>/dev/null
    done

    # 2. Remove symlinks and recreate files with correct permissions
    for logfile in /var/log/messages /var/log/daemon.log /var/log/debug /var/log/kern.log /var/log/user.log /var/log/syslog; do
        rm -f "$logfile"
        touch "$logfile"
        chmod 644 "$logfile"
        chown root:adm "$logfile" 2>/dev/null || chown root:root "$logfile"
    done

    # 3. Restart the services
    systemctl daemon-reload 2>/dev/null
    for srv in rsyslog syslog-ng syslog busybox-syslogd; do
        systemctl start "$srv" 2>/dev/null
        /etc/init.d/"$srv" start 2>/dev/null
    done
}

# Set the trap to run cleanup on exit
trap cleanup EXIT

# 1. Silence the terminal console
dmesg -n 1

# 2. Redirect all active log files to /dev/null
# This clears the space and prevents future growth
for logfile in /var/log/messages /var/log/daemon.log /var/log/debug /var/log/kern.log /var/log/user.log /var/log/syslog; do
    rm -f "$logfile"
    ln -s /dev/null "$logfile"
done

# 3. Kill and restart the logging services so they 
# pick up the new "Black Hole" symlinks
systemctl restart rsyslog 2>/dev/null
systemctl restart syslog-ng 2>/dev/null
/etc/init.d/syslog restart 2>/dev/null


# Default to relative path, but allow override via environment variable. Helpful for dev vs prod env
VISIONAI_PATH="${VISIONAI_PATH_OVERRIDE:-./visionai.py}"

# Qprof essentials
export QMONITOR_BACKEND_LIB_PATH=/var/QualcommProfiler/libs/backends/
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/var/QualcommProfiler/libs/
export PATH=$PATH:/data/shared/QualcommProfiler/bins

export XDG_RUNTIME_DIR=/dev/socket/weston
export WAYLAND_DISPLAY=wayland-1

export GST_DEBUG=qtiml*:1
export ADSP_LIBRARY_PATH="/usr/lib/rfsa/adsp;/dsp"
export QNN_OPTIONS="log_severity_level:3"
export ADSP_DEBUG=0
export FARPC_DEBUG_LEVEL=0
export ADSP_LOG_LEVEL=1
export QTI_LOG_LEVEL=1
export QNN_LOG_LEVEL=0    

"$VISIONAI_PATH" > /dev/null 2>&1
