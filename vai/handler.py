import pathlib
import signal
import subprocess
import sys
from time import sleep

import gi

from .common import (
    APP_NAME,
    CAMERA,
    CLASSIFICATION,
    CPU_THERMAL_KEY,
    CPU_UTIL_KEY,
    DEFAULT_DUAL_WINDOW,
    DEFAULT_LEFT_WINDOW,
    DEPTH_SEGMENTATION,
    GPU_THERMAL_KEY,
    GPU_UTIL_KEY,
    MEM_THERMAL_KEY,
    MEM_UTIL_KEY,
    DSP_UTIL_KEY,
    OBJECT_DETECTION,
    POSE_DETECTION,
    SEGMENTATION,
    HW_SAMPLING_PERIOD_ms,
)
from .gst_thread import GstPipeline
from .psutil_profile import get_cpu_gpu_mem_temps

# Locks app version, prevents warnings
gi.require_version("Gtk", "3.0")

from gi.repository import GLib, Gtk

# Tuning variable to adjust the height of the video display
HEIGHT_OFFSET = 17
MAX_WINDOW_WIDTH = 1920 // 2
MAX_WINDOW_HEIGHT = 720

DUAL_WINDOW_DEMOS = ["depth segmentation"]

PIPELINE_HEALTH_SIGNAL = "identity signal-handoffs=true name=id"


class Handler:
    def __init__(self, display_fps_metrics=True):
        self.demoList = [
            None,
            CAMERA,
            POSE_DETECTION,
            SEGMENTATION,
            CLASSIFICATION,
            OBJECT_DETECTION,
            DEPTH_SEGMENTATION,
        ]
        self.demoProcess0 = None
        self.demoProcess1 = None
        self.QProf = None
        self.frame0 = None
        self.frame1 = None
        # These values should be determined by GUI's allocation (IE glade's config)
        self.allocated_sizes = False
        self.DrawArea1_x = None
        self.DrawArea1_y = None
        self.DrawArea1_w = None
        self.DrawArea1_h = None
        self.DrawArea2_x = None
        self.DrawArea2_y = None
        self.DrawArea2_w = None
        self.DrawArea2_h = None
        self.display_fps_metrics = display_fps_metrics
        self.USBCameras = []
        self.dualDemoRunning0 = False
        self.dualDemoRunning1 = False
        self.CycleDemo0 = False
        self.CycleDemo1 = False

        # TODO: protect with sync primitive?
        self.sample_data = {
            CPU_UTIL_KEY: 0,
            MEM_UTIL_KEY: 0,
            GPU_UTIL_KEY: 0,
            DSP_UTIL_KEY: 0,
            CPU_THERMAL_KEY: 0,
            MEM_THERMAL_KEY: 0,
            GPU_THERMAL_KEY: 0,
        }
        # TODO: scan_for_connected_cameras() to include MIPI
        self.USBCameraCount = self.scan_for_connected_usb_cameras()
        self.cam1 = self.USBCameras[0][1] if self.USBCameraCount > 0 else None
        self.cam2 = self.USBCameras[1][1] if self.USBCameraCount > 1 else None

        print(f"Using CAM1: {self.cam1}")
        print(f"Using CAM2: {self.cam2}")

        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self.exit, "SIGINT")
        GLib.timeout_add(HW_SAMPLING_PERIOD_ms, self.update_sample_data)

    # TODO: MIPI integration
    def scan_for_connected_usb_cameras(self):
        """Scans for cameras via v4l, populating the USBCameras list with the camera name and path, returning the number of cameras found."""

        usb_cameras_path = pathlib.Path("/dev/v4l/by-id")
        if not usb_cameras_path.exists():
            print(
                "Warning: no USB cameras found. Please examine your USB camera connections."
            )
            return 0

        try:
            output = subprocess.check_output(["ls", "/dev/v4l/by-id"])
            device_id = -1
            for device_info in output.decode().splitlines():
                # By testing, video-index0 is the camera capable of video streaming
                if "video-index0" in device_info:
                    device_id = device_id + 1
                    self.USBCameras.append(
                        ("USB CAM" + str(device_id), "/dev/v4l/by-id/" + device_info)
                    )
        except Exception as e:
            print(f"Error scanning for USB cameras: {e}")
        finally:
            return len(self.USBCameras)

    def exit(self, payload):
        """Handle exit signals and clean up resources before exiting the application.

        Due to the threaded nature of the application, this function needs to be carefully linked with Gtk
        """

        exit_message = f"Exiting {APP_NAME}" + (f" due to {payload}" if payload else "")
        print(f"\n{exit_message}")

        Gtk.main_quit()
        # Unclear if Max meant to register the mainWindow destroy function,
        # but it doesn't appear to be registered right now so call it manually
        self.on_mainWindow_destroy()

        sys.exit(0)

    def update_temps(self):
        cpu_temp, gpu_temp, mem_temp = get_cpu_gpu_mem_temps()

        self.sample_data[CPU_THERMAL_KEY] = cpu_temp
        if cpu_temp is not None:
            GLib.idle_add(
                self.IdleUpdateLabels,
                self.CPU_temp,
                "{:.2f}".format(cpu_temp, 2),
            )
        self.sample_data[GPU_THERMAL_KEY] = gpu_temp
        if gpu_temp is not None:
            GLib.idle_add(
                self.IdleUpdateLabels,
                self.GPU_temp,
                "{:.2f}".format(gpu_temp, 2),
            )
        self.sample_data[MEM_THERMAL_KEY] = mem_temp
        if mem_temp is not None:
            GLib.idle_add(
                self.IdleUpdateLabels,
                self.MEM_temp,
                "{:.2f}".format(mem_temp, 2),
            )

        return True

    def update_loads(self):
        cpu_util, gpu_util, mem_util, dsp_util = (
            self.QProf.get_cpu_usage_pct(),
            self.QProf.get_gpu_usage_pct(),
            self.QProf.get_memory_usage_pct(),
            self.QProf.get_dsp_usage_pct(),
        )
        self.sample_data[CPU_UTIL_KEY] = cpu_util
        self.sample_data[GPU_UTIL_KEY] = gpu_util
        self.sample_data[MEM_UTIL_KEY] = mem_util
        self.sample_data[DSP_UTIL_KEY] = dsp_util
        GLib.idle_add(
            self.IdleUpdateLabels,
            self.CPU_load,
            "{:.2f}".format(cpu_util, 2),
        )
        GLib.idle_add(
            self.IdleUpdateLabels,
            self.GPU_load,
            "{:.2f}".format(gpu_util, 2),
        )
        GLib.idle_add(
            self.IdleUpdateLabels,
            self.MEM_load,
            "{:.2f}".format(mem_util, 2),
        )
        GLib.idle_add(
            self.IdleUpdateLabels,
            self.DSP_load,
            "{:.2f}".format(dsp_util, 2),
        )
        return True

    def update_sample_data(self):
        return self.update_temps() and self.update_loads()

    def close_about(self, *args):
        self.aboutWindow.hide()

    def open_about(self, *args):
        self.aboutWindow.set_transient_for(self.MainWindow)
        self.aboutWindow.run()

    def on_mainWindow_destroy(self, *args):
        if self.QProf is not None:
            self.QProf.Close()

        if self.demoProcess0 is not None:
            self.demoProcess0.close()

        if self.demoProcess1 is not None:
            self.demoProcess1.close()

        Gtk.main_quit(*args)

    def _modify_command_pipeline(
        self, command, stream_index, inject_health_signal=True
    ):
        """Modify GST pipeline by replacing placeholders with runtime values."""

        # TODO: support l/r windows through parameterization or other technique
        displaysink_text = (
            "fpsdisplaysink text-overlay=true video-sink="
            if self.display_fps_metrics
            else ""
        )

        # NOTE: if fpsdisplaysink is used, the video-sink property needs wrapped; "" does that
        command = command.replace(
            "<SINGLE_DISPLAY>",
            f'{displaysink_text}"{DEFAULT_LEFT_WINDOW}"',
        )
        command = command.replace(
            "<DUAL_DISPLAY>",
            f'{displaysink_text}"{DEFAULT_DUAL_WINDOW}"',
        )

        # TODO: If we do file processing, we'll need to support that around here
        health_monitor_addin = (
            " ! " + PIPELINE_HEALTH_SIGNAL if inject_health_signal else ""
        )
        command = command.replace(
            "<DATA_SRC>",
            (
                f"v4l2src device={self.cam1 if stream_index == 0 else self.cam2}"
                + health_monitor_addin
            ),
        )
        # TODO: use rect instead of x/y/width/height ?
        x = self.DrawArea1_x if stream_index == 0 else self.DrawArea2_x
        y = self.DrawArea1_y if stream_index == 0 else self.DrawArea2_y
        w = self.DrawArea1_w if stream_index == 0 else self.DrawArea2_w
        h = self.DrawArea1_h if stream_index == 0 else self.DrawArea2_h
        command = command.replace(
            "<ONE_WINDOW_XYWH>",
            f"x={x} y={y} width={w} height={h}",
        )
        # WARN: Stream index doesnt matter here. Its essential the dual window starts at drawarea1 and is 2*w wide
        command = command.replace(
            "<DUAL_WINDOW_XYWH>",
            f"x={self.DrawArea1_x} y={self.DrawArea1_y} width={2*w} height={h}",
        )
        return command

    def update_window_allocations(self):
        """Dynamically determine the size and position of the video windows based on the current GUI partitioning."""

        # TODO: Scale dual window res to draw area size. Draw Area needs to have constrants and be centered, so this is a tempororary solution
        # IE, remove the hardcoded vals
        if not self.allocated_sizes:
            # TODO: Pull up allocation/sizing to previous function closer to init
            allocation = self.DrawArea1.get_allocation()
            self.DrawArea1_x = allocation.x
            self.DrawArea1_y = allocation.y
            self.DrawArea1_w = allocation.width
            self.DrawArea1_h = allocation.height

            allocation = self.DrawArea2.get_allocation()
            self.DrawArea2_x = allocation.x
            self.DrawArea2_y = allocation.y
            self.DrawArea2_w = allocation.width
            self.DrawArea2_h = allocation.height

            self.allocated_sizes = True

    def getCommand(self, demoIndex, stream_index):
        self.update_window_allocations()
        # TODO: just use combo.get_active_id() instead of index. Then map into demo directly
        command = self.demoList[demoIndex][:]
        command = self._modify_command_pipeline(command, stream_index)
        print(command)
        return command

    def kill_demos(self, demo_process, demo_selection_combo):
        """Kill the demo process if it is running. Might have to kill multiple demos depending up next queued demo."""

        demo = demo_selection_combo.get_active_id()
        kill0 = True if demo_process == 0 else False
        kill1 = True if demo_process == 1 else False
        if demo.lower() in DUAL_WINDOW_DEMOS:
            if demo_process == 0:
                self.dualDemoRunning0 = True
            if demo_process == 1:
                self.dualDemoRunning1 = True

            kill0 = True
            kill1 = True
        else:
            if demo_process == 0:
                self.dualDemoRunning0 = False
            if demo_process == 1:
                self.dualDemoRunning1 = False

        if kill0 and self.demoProcess0 is not None:
            self.demoProcess0.close()
            self.demoProcess0 = None
        if kill1 and self.demoProcess1 is not None:
            self.demoProcess1.close()
            self.demoProcess1 = None
        sleep(1)

    def demo0_selection_changed_cb(self, combo):
        """Signal handler for the 1st demo selection combo box."""
        self.kill_demos(0, combo)
        index = combo.get_active()
        if index == 0:
            self.demoProcess0 = None
            self.CycleDemo0 = False
        else:
            self.CycleDemo0 = True
            self.demoProcess0 = GstPipeline(self.getCommand(index, 0), 'process0')
            self.demoProcess0.start()

    def demo1_selection_changed_cb(self, combo):
        """Signal handler for the 2nd demo selection combo box."""
        self.kill_demos(1, combo)
        index = combo.get_active()
        if index == 0:
            self.demoProcess1 = None
            self.CycleDemo1 = False
        else:
            self.CycleDemo1 = True
            self.demoProcess1 = GstPipeline(self.getCommand(index, 1), 'process1')
            self.demoProcess1.start()

    def IdleUpdateLabels(self, label, text):
        GLib.idle_add(label.set_text, text)

    # TODO: Verify then delete CapImage calls
    def CapImage_event1(self, widget, context):
        raise RuntimeError("This function is not needed in the current implementation")

    def CapImage_event2(self, widget, context):
        raise RuntimeError("This function is not needed in the current implementation")
