import multiprocessing as mp
import pathlib
import subprocess
import os
from vai.qprofile import QProfProcess
from vai.pipeline_process import gstreamer_process
import time
import threading
import queue as q_lib
import gi
gi.require_version("Gtk", "3.0")
gi.require_version('Gst', '1.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gst, GdkPixbuf

from .common import (
    APP_NAME,
    CAMERA,
    CLASSIFICATION,
    CPU_THERMAL_KEY,
    CPU_UTIL_KEY,
    USB_CAM_CAPS,
    MIPI_CAM_CAPS,
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
    AUTOMATIC_DEMO_SWITCH_s,
    QUIT_CLEANUP_DELAY_ms
)
from .temp_profile import get_cpu_gpu_mem_temps

# needed to release gstreamer with cv2
os.environ['OPENCV_VIDEOIO_PRIORITY_MSMF'] = '0'

# Tuning variable to adjust the height of the video display
HEIGHT_OFFSET = 17
MAX_WINDOW_WIDTH = 1920 // 2
MAX_WINDOW_HEIGHT = 720
MIPI_CSI_CAMERA_SCAN_TIMEOUT = 5
CAMERA_SCAN_DELAY_ms = 3000
CLOSE_APPLICATION_DELAY = 2
PIPELINE_THREAD_PAUSE_s = 0.1

DUAL_WINDOW_DEMOS = ["add drop down items here if needed"]

PIPELINE_HEALTH_SIGNAL = "identity signal-handoffs=true name=id"

class Handler:
    def __init__(self):

        self.queue0 = mp.Queue(maxsize=10)
        self.queue1 = mp.Queue(maxsize=10)

        self.demoList = [
            None,
            CAMERA,
            POSE_DETECTION,
            SEGMENTATION,
            CLASSIFICATION,
            OBJECT_DETECTION,
            DEPTH_SEGMENTATION,
        ]

        self.QProf = QProfProcess()
        self.MainWindowShown = False
        self.MainWindow = None
        self.aboutWindow = None
        self.FPSRate0 = None
        self.FPSRate1 = None
        self.CPU_load = None
        self.GPU_load = None
        self.DSP_load = None
        self.MEM_load = None
        self.CPU_temp = None
        self.GPU_temp = None
        self.MEM_temp = None
        self.TopBox = None
        self.DataGrid = None
        self.BottomBox = None
        self.DrawArea1 = None
        self.DrawArea2 = None
        self.AspectFrame1 = None
        self.AspectFrame2 = None
        self.GraphDrawAreaTop = None
        self.GraphDrawAreaBottom = None
        self.demo_selection0 = None
        self.demo_selection1 = None
        self.systemCameras = []
        self.dualDemoRunning0 = False
        self.dualDemoRunning1 = False
        self.CycleDemo0 = False
        self.CycleDemo1 = False
        self.demoSelection0Cnt = 0
        self.demoSelection1Cnt = 0

        self.Pipeline0 = None
        self.Pipeline1 = None
        self.Pipeline0closing = False
        self.Pipeline1closing = False
        self.Pipeline0Sink = None
        self.Pipeline1Sink = None
        self.Pipeline0StopEvent = mp.Event()
        self.Pipeline1StopEvent = mp.Event()

        GLib.timeout_add(10, self.on_frame_received_pipe0)
        GLib.timeout_add(10, self.on_frame_received_pipe1)

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
        GLib.timeout_add(HW_SAMPLING_PERIOD_ms, self.update_sample_data)
        GLib.timeout_add(1000, self.automateDemo)


    def set_video_sink(self, index, sink):
        if index == 0:
            self.Pipeline0Sink = sink
        else:
            self.Pipeline1Sink = sink

    def StartPipeline(self, index, command):
        pipelines = {
            0: ('Pipeline0', 'Pipeline0StopEvent', 'queue0', 'Pipeline0closing'),
            1: ('Pipeline1', 'Pipeline1StopEvent', 'queue1', 'Pipeline1closing'),
        }
        
        attr_name, stop_event_attr, queue_attr, closing_attr = pipelines[index]
        stop_event = getattr(self, stop_event_attr)
        queue = getattr(self, queue_attr)

        if getattr(self, attr_name) is not None:
            self.StopPipeline(index)
            time.sleep(0.5)
        
        print(f"Initializing GStreamer subprocess in pipeline {index}...")
        stop_event.clear()
        process = mp.Process(target=gstreamer_process, args=(command, queue, stop_event))
        
        try:
            setattr(self, closing_attr, False)
            process.start()
            setattr(self, attr_name, process)
        except Exception as e:
            setattr(self, closing_attr, True)
            print(f"Unable to start pipeline {index}: {e}")   

    def StopPipeline(self, index):
        pipelines = {
            0: ('Pipeline0', 'Pipeline0StopEvent', 'queue0', 'Pipeline0closing'),
            1: ('Pipeline1', 'Pipeline1StopEvent', 'queue1', 'Pipeline1closing'),
        }
        
        attr_name, stop_event_attr, queue_attr, closing_attr = pipelines[index]
        current_pipe = getattr(self, attr_name)
        stop_event = getattr(self, stop_event_attr)
        queue = getattr(self, queue_attr)

        if current_pipe is None:
            return

        print("Requesting graceful stop...")
        stop_event.set()
        
        start_time = time.monotonic()
        while current_pipe.is_alive() and (time.monotonic() - start_time) < 10.0:
            try:
                queue.get_nowait()
            except q_lib.Empty:
                time.sleep(0.01)

        if current_pipe.is_alive():
            print("Process did not stop gracefully, forcing termination...")
            current_pipe.terminate()
            current_pipe.join(timeout=1)
            if current_pipe.is_alive():
                current_pipe.kill()
                current_pipe.join()

        setattr(self, closing_attr, True)
        setattr(self, attr_name, None)  # Clear the pipeline reference
        
        print("Pipeline stopped and cleaned up.")   

    def update_camera_information(self):
        self.cameraCount = self.scan_for_connected_cameras()
        self.cam1 = self.systemCameras[0][1] if self.cameraCount > 0 else None
        self.cam1Type = self.systemCameras[0][2] if self.cameraCount > 0 else None

        self.cam2 = self.systemCameras[1][1] if self.cameraCount > 1 else None
        self.cam2Type = self.systemCameras[1][2] if self.cameraCount > 1 else None

        if self.cam1:
            self.demo_selection0.set_sensitive(True)

        if self.cam2:
            self.demo_selection1.set_sensitive(True)

        print(f"Using CAM1: {self.cam1}")
        print(f"Using CAM2: {self.cam2}")
        self.close_dialog(self)
        return GLib.SOURCE_REMOVE
        
    def _probe_mipi_camera(self, camera_index, timeout_s=MIPI_CSI_CAMERA_SCAN_TIMEOUT):
        """
        Probes for a MIPI camera using GStreamer's Python API.
        Returns True if the camera is detected, False otherwise.
        """
        Gst.init(None)

        print(f"Probing for MIPI camera index: {camera_index} using GStreamer API...")
        
        src = Gst.ElementFactory.make("qtiqmmfsrc", f"mipi-probe-{camera_index}")
        if not src:
            print("  Error: Failed to create qtiqmmfsrc element. Is the plugin installed?")
            return False

        try:
            src.set_property("camera", camera_index)
        except TypeError:
            print(f"  Error: Could not set 'camera' property on qtiqmmfsrc. Is the element correct?")
            return False

        pipeline = Gst.Pipeline.new(f"mipi-probe-pipeline-{camera_index}")
        sink = Gst.ElementFactory.make("fakesink", f"mipi-probe-sink-{camera_index}")
        if not sink:
            print("  Error: Failed to create fakesink element.")
            # Clean up the source element if sink creation fails
            src.set_state(Gst.State.NULL)
            return False

        pipeline.add(src)
        pipeline.add(sink)
        if not src.link(sink):
            print(f"  Error: Could not link qtiqmmfsrc to fakesink for camera {camera_index}.")
            pipeline.set_state(Gst.State.NULL)
            return False

        # Attempt to set state to PAUSED. This will try to acquire the camera resource.
        state_change_return = pipeline.set_state(Gst.State.PAUSED)

        found = False
        # For a live source probe, SUCCESS and NO_PREROLL both indicate the device was acquired.
        if state_change_return == Gst.StateChangeReturn.SUCCESS or state_change_return == Gst.StateChangeReturn.NO_PREROLL:
            print(f"  Success: MIPI camera {camera_index} found (state change result: {state_change_return.value_nick}).")
            found = True
        elif state_change_return == Gst.StateChangeReturn.ASYNC:
            # Wait for async state change to complete or time out.
            # Timeout is in nanoseconds.
            _, current_state, _ = pipeline.get_state(timeout_s * Gst.SECOND)
            if current_state == Gst.State.PAUSED:
                print(f"  Success: MIPI camera {camera_index} found (state change was asynchronous).")
                found = True
            else:
                print(f"  Failure: MIPI camera {camera_index} timed out or failed to reach PAUSED state (final state: {current_state.value_nick}).")
                found = False
        else: # FAILURE
            print(f"  Failure: MIPI camera {camera_index} could not be opened (state change failed with: {state_change_return.value_nick}).")
            found = False

        # Always clean up
        pipeline.set_state(Gst.State.NULL)
        
        return found

    def scan_for_connected_cameras(self):
        """Scans for USB cameras via v4l, populating the USBCameras list with the camera name and path, returning the number of cameras found."""
        try:
            usb_cameras_path = pathlib.Path("/dev/v4l/by-id")
            print(f"Scanning for USB cameras...")
            if not usb_cameras_path.exists():
                print(
                    "Warning: no USB cameras found. Please examine your USB camera connections."
                )
            else:
                output = subprocess.check_output(["ls", "/dev/v4l/by-id"])
                device_id = -1
                for device_info in output.decode().splitlines():
                    # By testing, video-index0 is the camera capable of video streaming
                    if "video-index0" in device_info:
                        device_id = device_id + 1
                        self.systemCameras.append(
                            ("USB CAM" + str(device_id), "/dev/v4l/by-id/" + device_info, "usb")
                        )
        except Exception as e:
            print(f"Error scanning for USB cameras: {e}")

        """Scans for MIPI cameras via a gst-launch test only if there are less than 2 USB cameras."""
        if len(self.systemCameras) < 2:
            try:
                print(f"Scanning for MIPI-CSI cameras...")
                for camIndex in range(0,2):
                    try:
                        if self._probe_mipi_camera(camIndex, MIPI_CSI_CAMERA_SCAN_TIMEOUT):
                            self.systemCameras.append(
                                ("MIPI CAM" + str(camIndex), "camera=" + str(camIndex), "mipi")
                            )
                    except Exception as e:
                        print(f"MIPI camera={camIndex} failed: {e}")
            except Exception as e:
                print(f"Error scanning for MIPI-CSI cameras: {e}")
            
        return len(self.systemCameras)

    def update_temps(self):
        if not self.sample_data:
            return GLib.SOURCE_REMOVE
        
        cpu_temp, gpu_temp, mem_temp = get_cpu_gpu_mem_temps()

        self.sample_data[CPU_THERMAL_KEY] = cpu_temp
        if cpu_temp is not None:
            GLib.idle_add(self.CPU_temp.set_text, "{:6.2f}".format(cpu_temp))
        self.sample_data[GPU_THERMAL_KEY] = gpu_temp
        if gpu_temp is not None:
            GLib.idle_add(self.GPU_temp.set_text, "{:6.2f}".format(gpu_temp))
        self.sample_data[MEM_THERMAL_KEY] = mem_temp
        if mem_temp is not None:
            GLib.idle_add(self.MEM_temp.set_text, "{:6.2f}".format(mem_temp))

        return GLib.SOURCE_REMOVE

    def update_loads(self):
        if not self.sample_data:
            return GLib.SOURCE_REMOVE

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
        GLib.idle_add(self.CPU_load.set_text, "{:6.2f}".format(cpu_util))
        GLib.idle_add(self.GPU_load.set_text, "{:6.2f}".format(gpu_util))
        GLib.idle_add(self.MEM_load.set_text, "{:6.2f}".format(mem_util))
        GLib.idle_add(self.DSP_load.set_text, "{:6.2f}".format(dsp_util))
        return GLib.SOURCE_REMOVE

    def update_sample_data(self):
        # Run blocking I/O in separate threads to avoid freezing the UI.
        # The update functions will then schedule UI updates on the main thread.
        threading.Thread(target=self.update_temps, daemon=True).start()
        threading.Thread(target=self.update_loads, daemon=True).start()
        return GLib.SOURCE_CONTINUE

    def close_about(self, *args):
        if self.aboutWindow:
            self.aboutWindow.hide()

    def open_about(self, *args):
        if self.aboutWindow:
            self.aboutWindow.set_transient_for(self.MainWindow)
            self.aboutWindow.run()

    def on_mainWindow_destroy(self, *args):
        """Handle exit signals and clean up resources before exiting the application.

        Due to the threaded nature of the application, this function needs to be carefully linked with Gtk
        """
        print("Shutdown initiated...")
        if self.QProf is not None:
            self.QProf.Close()

        self.StopPipeline(0)
        self.StopPipeline(1)

        # Schedule the final shutdown sequence. This polling mechanism waits
        # for the async pipeline cleanup to complete.
        GLib.timeout_add(QUIT_CLEANUP_DELAY_ms, self.quit_application, *args)

    def quit_application(self, *args):
        print("Waiting for background threads to join...")
        # Join threads to ensure they exit cleanly before the main process
        if self.QProf and self.QProf.is_alive():
            self.QProf.Close()
            self.QProf.join(timeout=10.0)

        print("Exiting GTK main loop.")
        Gtk.main_quit(*args)
        return GLib.SOURCE_REMOVE # Stop the timer

    def close_dialog(self, *args):
        if self.dialogWindow:
            self.dialogWindow.hide()
        return GLib.SOURCE_REMOVE

    def show_message(self):
        if self.dialogWindow:
            self.dialogWindow.set_transient_for(self.MainWindow)
            self.dialogWindow.show_all()
        return GLib.SOURCE_REMOVE

    def on_mainWindow_show(self, *args):
        if not self.MainWindowShown:
            self.MainWindowShown = True
            GLib.idle_add(self.show_message)
            GLib.timeout_add(CAMERA_SCAN_DELAY_ms, self.update_camera_information)

    def _modify_command_pipeline(
        self, command, stream_index
    ):
        """Modify GST pipeline by replacing placeholders with runtime values."""
        if stream_index == 0 and self.cam1 != None:
            if self.cam1Type == "usb":
                command = command.replace("<DATA_SRC>",f"v4l2src device={self.cam1} name=videosource" + USB_CAM_CAPS)
                #command = command.replace("<DATA_SRC>",f"v4l2src io-mode=4 device={self.cam1} name=videosource" + USB_CAM_CAPS)
            elif self.cam1Type == "mipi":
                command = command.replace("<DATA_SRC>",f" qtiqmmfsrc {self.cam1} name=videosource" + MIPI_CAM_CAPS)
        elif self.cam2 != None:
            if self.cam2Type == "usb":
                command = command.replace("<DATA_SRC>",f"v4l2src device={self.cam2} name=videosource" + USB_CAM_CAPS)
            elif self.cam2Type == "mipi":
                command = command.replace("<DATA_SRC>",f" qtiqmmfsrc {self.cam2} name=videosource" + MIPI_CAM_CAPS)
        else:
            command = command.replace("<DATA_SRC>",f" videotestsrc name=videosource")
            
        return command

    def SwitchPipeline0(self, combo):
        index = combo.get_active()
        """This function is called after the old pipeline is confirmed to be stopped."""
        if index > 0:  # A demo other than "None" was selected
            self.CycleDemo0 = True
            command = self.demoList[index][:]
            command = self._modify_command_pipeline(command, 0)
            print(f"Starting pipeline 0: {command}")
            self.StartPipeline(0, command)
            self.Pipeline0Sink.show()
        else:  # "None" was selected
            self.CycleDemo0 = False
            self.StopPipeline(0)
            print("Pipeline 0 set to None.")
            self.Pipeline0Sink.hide()

    def SwitchPipeline1(self, combo):
        index = combo.get_active()
        """This function is called after the old pipeline is confirmed to be stopped."""
        if index > 0:  # A demo other than "None" was selected
            self.CycleDemo1 = True
            command = self.demoList[index][:]
            command = self._modify_command_pipeline(command, 1)
            print(f"Starting pipeline 1: {command}")
            self.StartPipeline(1, command)
            self.Pipeline1Sink.show()    
        else:  # "None" was selected
            self.CycleDemo1 = False
            self.StopPipeline(1)
            print("Pipeline 1 set to None.")
            self.Pipeline1Sink.hide()

    def demo0_selection_changed_cb(self, combo):
        """Signal handler for the 1st demo selection combo box."""
        # This is a GTK signal handler, so it runs on the main UI thread.
        # The SwitchPipeline function is non-blocking, so we can call it directly.
        self.demo0Interval = 0
        self.SwitchPipeline0(combo)

    def demo1_selection_changed_cb(self, combo):
        """Signal handler for the 2nd demo selection combo box."""
        # This is a GTK signal handler, so it runs on the main UI thread.
        # The SwitchPipeline function is non-blocking, so we can call it directly.
        self.demo1Interval = 0
        self.SwitchPipeline1(combo)

    def automateDemo(self):
        if not self.demo_selection0 or not self.demo_selection1:
            return
        
        if (self.CycleDemo0) and (self.demoSelection0Cnt > 0):
            cycleDemo0 = True
        else:
            cycleDemo0 = False
            self.demo0Interval = 0
            self.demo0RunningIndex = 1

        if (self.CycleDemo1) and (self.demoSelection1Cnt > 0):
            cycleDemo1 = True
        else:
            cycleDemo1 = False
            self.demo1Interval = 0
            self.demo1RunningIndex = 1

        if cycleDemo0:
            if self.demo0Interval >= AUTOMATIC_DEMO_SWITCH_s:
                self.demo0Interval = 0

                #time automation in such a way that only one demo switches at a time
                #to minimize potential issues
                self.demo1Interval = int(AUTOMATIC_DEMO_SWITCH_s / 2)

                self.demo0RunningIndex = self.demo0RunningIndex + 1

                if self.demo0RunningIndex >= self.demoSelection0Cnt:
                    self.demo0RunningIndex = 1
                
                self.demo_selection0.set_active(self.demo0RunningIndex) 
                
            else:
                self.demo0Interval = self.demo0Interval + 1

        if cycleDemo1:
            if self.demo1Interval >= AUTOMATIC_DEMO_SWITCH_s:
                self.demo1Interval = 0

                #force demo 1 to run a different demo
                if self.demo0RunningIndex >=0:
                    self.demo1RunningIndex = self.demo0RunningIndex + 1
                else:
                    self.demo1RunningIndex = self.demo1RunningIndex + 1

                if self.demo1RunningIndex >= self.demoSelection1Cnt:
                    self.demo1RunningIndex = 1

                self.demo_selection1.set_active(self.demo1RunningIndex) 
            else:
                self.demo1Interval = self.demo1Interval + 1

        return GLib.SOURCE_CONTINUE

    def on_frame_received_pipe0(self):
        if (self.Pipeline0 == None):
            return GLib.SOURCE_CONTINUE
        
        try:
            # Use non-blocking get to ensure the UI thread never hangs
            self.Pipeline0ImageArray = self.queue0.get_nowait()
            self.Pipeline0Sink.queue_draw()  # Trigger redraw
        except q_lib.Empty:
            pass
        return GLib.SOURCE_CONTINUE

    def on_frame_received_pipe1(self):
        if (self.Pipeline1 == None):
            return GLib.SOURCE_CONTINUE
        
        try:
            # Use non-blocking get to ensure the UI thread never hangs
            self.Pipeline1ImageArray = self.queue1.get_nowait()
            self.Pipeline1Sink.queue_draw()  # Trigger redraw
        except q_lib.Empty:
            pass
        return GLib.SOURCE_CONTINUE

    def on_draw_pipe0(self, widget, cr):
        allocation = widget.get_allocation()

        if hasattr(self, 'Pipeline0ImageArray') and (self.Pipeline0closing == False):
            h, w, _ = self.Pipeline0ImageArray.shape
            if w > 0 and h > 0:
                scale = min(allocation.width / w, allocation.height / h)
                cr.translate((allocation.width - w * scale) / 2, (allocation.height - h * scale) / 2)
                cr.scale(scale, scale)

            data = self.Pipeline0ImageArray.tobytes()
            pixbuf = GdkPixbuf.Pixbuf.new_from_data(
                data, GdkPixbuf.Colorspace.RGB, False, 8, w, h, w * 3, None, None
            )
            Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
            cr.paint()
        return GLib.SOURCE_REMOVE

    def on_draw_pipe1(self, widget, cr):
        allocation = widget.get_allocation()

        if hasattr(self, 'Pipeline1ImageArray') and (self.Pipeline1closing == False):
            h, w, _ = self.Pipeline1ImageArray.shape
            if w > 0 and h > 0:
                scale = min(allocation.width / w, allocation.height / h)
                cr.translate((allocation.width - w * scale) / 2, (allocation.height - h * scale) / 2)
                cr.scale(scale, scale)

            data = self.Pipeline1ImageArray.tobytes()
            pixbuf = GdkPixbuf.Pixbuf.new_from_data(
                data, GdkPixbuf.Colorspace.RGB, False, 8, w, h, w * 3, None, None
            )
            Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
            cr.paint()
        return GLib.SOURCE_REMOVE