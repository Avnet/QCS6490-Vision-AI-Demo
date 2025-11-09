import pathlib
import subprocess
import os
from vai.qprofile import QProfProcess
import gi
import threading
from gi.repository import Gdk

from .common import (
    APP_NAME,
    CAMERA,
    CLASSIFICATION,
    CPU_THERMAL_KEY,
    CPU_UTIL_KEY,
    DEFAULT_SINK,
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

# Locks app version, prevents warnings
gi.require_version("Gtk", "3.0")
gi.require_version('Gst', '1.0') 

from gi.repository import GLib, Gtk, Gst

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

class Pipeline:
    def __init__(self, name, main_loop, main_context):
        self.name = name
        self.main_loop = main_loop
        self.main_context = main_context
        self.pipeline = None
        self.videosink = None
        self.is_stopping = False

    def set_sink(self, sink):
        self.videosink = sink
        return GLib.SOURCE_REMOVE

    def start(self, command):
        """Parse, configure, and start the GStreamer pipeline."""
        if self.pipeline:
            print(f"[{self.name}] Warning: Pipeline already running. Stop it first.")
            return GLib.SOURCE_REMOVE

        print(f"[{self.name}] Assigning command and starting stream...")
        self.pipeline = Gst.parse_launch(command)

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)
        self.pipeline.set_auto_flush_bus(True)
        self.pipeline.iterate_elements().foreach(self._set_queue_properties)

        videosink_element = self.pipeline.get_by_name("videosink")
        if videosink_element:
            videosink_widget = videosink_element.props.video_sink.props.widget
            # Schedule linking the widget to the UI on the main GTK thread
            # This function will then trigger setting the pipeline to PLAYING.
            GLib.idle_add(self._link_stream_to_gtk, videosink_widget)
        else:
            print(f"[{self.name}] Error: no 'videosink' element found in the pipeline.")
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None

        return GLib.SOURCE_REMOVE

    def stop(self, on_stopped_callback=None):
        """Stop and clean up the GStreamer pipeline."""
        if not self.pipeline:
            # Pipeline is already fully stopped.
            if on_stopped_callback:
                GLib.idle_add(on_stopped_callback)
            return GLib.SOURCE_REMOVE

        # If a stop is already in progress, just update the callback to the latest one.
        # The ongoing stop process will then trigger this new callback when it's done.
        self._on_stopped_callback = on_stopped_callback

        if self.is_stopping:
            # A stop is already underway. The callback has been updated. Nothing more to do.
            print(f"[{self.name}] Stop already in progress. Updating callback.")
            return GLib.SOURCE_REMOVE

        # This is a new stop request.
        print(f"[{self.name}] Stopping pipeline...")
        self.is_stopping = True
        # Request state change to NULL. The on_message handler will complete the cleanup.
        ret = self.pipeline.set_state(Gst.State.NULL)
        if ret == Gst.StateChangeReturn.ASYNC:
            print(f"[{self.name}] Waiting for pipeline to stop asynchronously...")
        else:
            # If the state change is not async, it's either already stopped (SUCCESS)
            # or failed. In either case, we should finalize immediately to un-stick the state.
            print(f"[{self.name}] Pipeline stop was not async (ret={ret.value_nick}). Finalizing immediately.")
            self._finalize_stop()

        return GLib.SOURCE_REMOVE

    def _finalize_stop(self):
        """Performs the actual resource cleanup after pipeline state is NULL."""
        print(f"[{self.name}] Finalizing pipeline stop.")
        if not self.pipeline:
            return
 
        # Schedule UI cleanup on the main GTK thread
        GLib.idle_add(self._clear_gtkbox)

        # Clean up GStreamer resources
        bus = self.pipeline.get_bus()
        if bus:
            bus.remove_signal_watch()
        
        self.pipeline = None
        self.is_stopping = False
        print(f"[{self.name}] Pipeline stopped and cleaned up.")

        # If a callback was provided, schedule it on the main thread.
        if hasattr(self, '_on_stopped_callback') and self._on_stopped_callback:
            GLib.idle_add(self._on_stopped_callback)
            self._on_stopped_callback = None

    def on_message(self, bus, message):
        t = message.type

        if t == Gst.MessageType.EOS:
            print(f"[{self.name}] Got EOS from sink pipeline")

        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"[{self.name}][{message.src.get_name()}] Error: {err.message}")

        elif t == Gst.MessageType.STATE_CHANGED:
            # We only care about messages from the pipeline itself
            if message.src == self.pipeline:
                old_state, new_state, pending_state = message.parse_state_changed()
                print(f"[{self.name}] Pipeline state changed from {old_state.value_nick} to {new_state.value_nick}.")
                # If we were stopping and the new state is NULL, finalize the cleanup
                if self.is_stopping and new_state == Gst.State.NULL:
                    self._finalize_stop() # This runs on the GStreamer thread
        return True

    def _link_stream_to_gtk(self, videosink_widget):
        self.videosink.pack_start(videosink_widget, True, True, 0)
        videosink_widget.show()
        # Now that the widget is part of the UI, we can tell the pipeline to play.
        # This must be scheduled on the GStreamer thread's context.
        GLib.idle_add(self._set_pipeline_to_playing, context=self.main_context)
        return GLib.SOURCE_REMOVE

    def _set_pipeline_to_playing(self):
        """Sets the pipeline to PLAYING state. Should be called from the GStreamer thread."""
        if self.pipeline:
            print(f"[{self.name}] UI sink ready. Setting pipeline to PLAYING.")
            self.pipeline.set_state(Gst.State.PLAYING)
        return GLib.SOURCE_REMOVE

    def _clear_gtkbox(self):
        #clear previous elements
        for child in self.videosink.get_children():
            self.videosink.remove(child)
        return GLib.SOURCE_REMOVE

    def _set_queue_properties(self, element):
        if element.get_factory().get_name().startswith('queue'):
            element.set_property("max-size-buffers", 10)
            element.set_property("max-size-bytes", 1 * 1024 * 1024)  # 1 MB
            element.set_property("max-size-time", 0.1 * Gst.SECOND)  # 0.1 second
            element.set_property("leaky", 2) 

    def _check_pipeline_state(self):
        """Checks and prints the current state of the pipeline."""
        state_return, state, pending = self.pipeline.get_state(Gst.CLOCK_TIME_NONE) # Get state immediately
        if state_return == Gst.StateChangeReturn.SUCCESS:
            #print(f"Pipeline is in state: {state.value_nick}")
            return state
        else:
            print(f"Failed to get pipeline state. Return: {state_return}")
            return state

class PipelineCtrl:
    def __init__(self):
        self.gstreamer_main_loop = None
        self.gstreamer_main_context = None
        self.gst_thread_started = threading.Event()

        # Start the GStreamer thread
        self.gst_thread = threading.Thread(target=self._gstreamer_thread_main, name="GstLoopThread")
        self.gst_thread.start()

        # Wait for the GStreamer loop to initialize
        self.gst_thread_started.wait(timeout=2)
        if not self.gstreamer_main_loop:
            raise RuntimeError("GStreamer thread failed to initialize.")

        self.Pipeline0 = Pipeline("pipeline-0", self.gstreamer_main_loop, self.gstreamer_main_context)
        self.Pipeline1 = Pipeline("pipeline-1", self.gstreamer_main_loop, self.gstreamer_main_context)

    def _gstreamer_thread_main(self):
        """This function runs in the separate GStreamer thread."""
        # 1. Create a new GMainContext for this thread.
        self.gstreamer_main_context = GLib.MainContext.new()

        # 2. Set this context as the thread's default.
        self.gstreamer_main_context.push_thread_default()

        # 3. Create a GLib.MainLoop using this context.
        self.gstreamer_main_loop = GLib.MainLoop.new(self.gstreamer_main_context, False)
        self.gst_thread_started.set() # Signal that the loop is ready

        print(f"GStreamer thread: MainLoop started in thread {threading.current_thread().name}")
        self.gstreamer_main_loop.run()

        # Clean up after the loop exits
        print(f"GStreamer thread: MainLoop finished in thread {threading.current_thread().name}")
        self.gstreamer_main_context.pop_thread_default() # Unset the thread default context

    def set_video_sink(self, index, sink):
        if index == 0:
            GLib.idle_add(self.Pipeline0.set_sink, sink, context=self.gstreamer_main_context)
        else:
            GLib.idle_add(self.Pipeline1.set_sink, sink, context=self.gstreamer_main_context)
    
    def start_pipeline(self, index, command):
        if index == 0:
            GLib.idle_add(self.Pipeline0.start, command, context=self.gstreamer_main_context)
        else:
            GLib.idle_add(self.Pipeline1.start, command, context=self.gstreamer_main_context)

    def stop_pipeline(self, index, on_stopped_callback=None):
        pipeline_to_stop = self.Pipeline0 if index == 0 else self.Pipeline1
        # Schedule the stop command on the GStreamer thread, passing the callback
        GLib.idle_add(pipeline_to_stop.stop, on_stopped_callback, context=self.gstreamer_main_context)

    def pipelines_finished(self):
        return True if self.Pipeline0.pipeline == None and self.Pipeline1.pipeline == None else False

    def quit_gstreamer_main_loop(self):
        if self.gstreamer_main_loop and self.gstreamer_main_loop.is_running():
            self.gstreamer_main_loop.quit()

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

        self.QProf = QProfProcess()
        self.pipelineCtrl = PipelineCtrl()
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
        self.display_fps_metrics = display_fps_metrics
        self.systemCameras = []
        self.dualDemoRunning0 = False
        self.dualDemoRunning1 = False
        self.CycleDemo0 = False
        self.CycleDemo1 = False
        self.demoSelection0Cnt = 0
        self.demoSelection1Cnt = 0

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
        self.pipelineCtrl.set_video_sink(index, sink)

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

        # Asynchronously stop the pipelines. The stop() method will ensure
        # resources are released cleanly when the state change is complete.
        self.pipelineCtrl.stop_pipeline(0)
        self.pipelineCtrl.stop_pipeline(1)

        # Schedule the final shutdown sequence. This polling mechanism waits
        # for the async pipeline cleanup to complete.
        GLib.timeout_add(QUIT_CLEANUP_DELAY_ms, self.quit_application, *args)

    def quit_application(self, *args):
        # This check is now meaningful. It will be false until the pipelines
        # have fully transitioned to NULL and set their self.pipeline to None.
        if self.pipelineCtrl.pipelines_finished():
            print("All pipelines cleaned up. Quitting GStreamer loop.")
            self.pipelineCtrl.quit_gstreamer_main_loop()

            print("Waiting for background threads to join...")
            # Join threads to ensure they exit cleanly before the main process
            if self.QProf and self.QProf.is_alive():
                self.QProf.join(timeout=2.0)
            if self.pipelineCtrl.gst_thread and self.pipelineCtrl.gst_thread.is_alive():
                self.pipelineCtrl.gst_thread.join(timeout=2.0)

            print("Exiting GTK main loop.")
            Gtk.main_quit(*args)
            return GLib.SOURCE_REMOVE # Stop the timer
        else:
            print("Waiting for pipelines to finish cleanup...")
            return GLib.SOURCE_CONTINUE

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
            "<DISPLAY_SINK>",
            f'{displaysink_text}{DEFAULT_SINK}',
        )

        # TODO: If we do file processing, we'll need to support that around here
        health_monitor_addin = (
            " ! " + PIPELINE_HEALTH_SIGNAL if inject_health_signal else ""
        )
        
        if stream_index == 0 and self.cam1 != None:
            if self.cam1Type == "usb":
                command = command.replace("<DATA_SRC>",f"v4l2src device={self.cam1} name=videosource" + USB_CAM_CAPS + health_monitor_addin)
            elif self.cam1Type == "mipi":
                command = command.replace("<DATA_SRC>",f" qtiqmmfsrc {self.cam1} name=videosource" + MIPI_CAM_CAPS + health_monitor_addin)
        elif self.cam2 != None:
            if self.cam2Type == "usb":
                command = command.replace("<DATA_SRC>",f"v4l2src device={self.cam2} name=videosource" + USB_CAM_CAPS + health_monitor_addin)
            elif self.cam2Type == "mipi":
                command = command.replace("<DATA_SRC>",f" qtiqmmfsrc {self.cam2} name=videosource" + MIPI_CAM_CAPS + health_monitor_addin)
        else:
            command = command.replace("<DATA_SRC>",f" videotestsrc name=videosource" + health_monitor_addin)
            
        return command

    def SwitchPipeline0(self, combo):
        index = combo.get_active()

        def start_new_pipeline():
            """This function is called after the old pipeline is confirmed to be stopped."""
            if index > 0:  # A demo other than "None" was selected
                self.CycleDemo0 = True
                command = self.demoList[index][:]
                command = self._modify_command_pipeline(command, 0)
                print(f"Starting pipeline 0: {command}")
                self.pipelineCtrl.start_pipeline(0, command)
                self.DrawArea1.override_background_color(
                    Gtk.StateType.NORMAL, Gdk.RGBA(0, 0, 0, 1)
                )                
            else:  # "None" was selected
                self.CycleDemo0 = False
                print("Pipeline 0 set to None.")
                self.DrawArea1.override_background_color(
                    Gtk.StateType.NORMAL, Gdk.RGBA(0, 0, 0, 0)
                )                

        # Stop the current pipeline and, upon completion, execute the callback to start the new one.
        # This is non-blocking and prevents the race condition.
        self.pipelineCtrl.stop_pipeline(0, on_stopped_callback=start_new_pipeline)

    def SwitchPipeline1(self, combo):
        index = combo.get_active()

        def start_new_pipeline():
            """This function is called after the old pipeline is confirmed to be stopped."""
            if index > 0:  # A demo other than "None" was selected
                self.CycleDemo1 = True
                command = self.demoList[index][:]
                command = self._modify_command_pipeline(command, 1)
                print(f"Starting pipeline 1: {command}")
                self.pipelineCtrl.start_pipeline(1, command)
                self.DrawArea2.override_background_color(
                    Gtk.StateType.NORMAL, Gdk.RGBA(0, 0, 0, 1)
                )                

            else:  # "None" was selected
                self.CycleDemo1 = False
                print("Pipeline 1 set to None.")
                self.DrawArea2.override_background_color(
                    Gtk.StateType.NORMAL, Gdk.RGBA(0, 0, 0, 0)
                )                

        # Stop the current pipeline and, upon completion, execute the callback to start the new one.
        self.pipelineCtrl.stop_pipeline(1, on_stopped_callback=start_new_pipeline)

    def demo0_selection_changed_cb(self, combo):
        """Signal handler for the 1st demo selection combo box."""
        # This is a GTK signal handler, so it runs on the main UI thread.
        # The SwitchPipeline function is non-blocking, so we can call it directly.
        self.SwitchPipeline0(combo)

    def demo1_selection_changed_cb(self, combo):
        """Signal handler for the 2nd demo selection combo box."""
        # This is a GTK signal handler, so it runs on the main UI thread.
        # The SwitchPipeline function is non-blocking, so we can call it directly.
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
