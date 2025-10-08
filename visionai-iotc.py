#!/usr/bin/env python3

import collections
import os
import threading
import time

import gi

import sys  # needed for sys.exit() on fatal errors or clean shutdown

# ADDITION: import IOTCONNECT SDK classes
from avnet.iotconnect.sdk.lite import Client, DeviceConfig, Callbacks, C2dAck, DeviceConfigError

from vai.common import (APP_HEADER, CPU_THERMAL_KEY, CPU_UTIL_KEY,
                        GPU_THERMAL_KEY, GPU_UTIL_KEY, GRAPH_SAMPLE_SIZE,
                        MEM_THERMAL_KEY, MEM_UTIL_KEY, TIME_KEY, TRIA,
                        TRIA_BLUE_RGBH, TRIA_PINK_RGBH, TRIA_YELLOW_RGBH,
                        AUTOMATIC_DEMO_SWITCH_s, GRAPH_SAMPLE_WINDOW_SIZE_s,
                        get_ema)
from vai.graphing import (draw_axes_and_labels,
                          draw_graph_background_and_border, draw_graph_data)
from vai.handler import Handler
from vai.qprofile import QProfProcess

# Existing signal handler for graceful exit
import signal
def signal_handler(sig, frame):
    print("Exiting application gracefully...")
    Gtk.main_quit()

signal.signal(signal.SIGINT, signal_handler)

# os.environ["XDG_RUNTIME_DIR"] = "/dev/socket/weston"
# os.environ["WAYLAND_DISPLAY"] = "wayland-1"
# os.environ["GDK_BACKEND"] = "wayland"
# os.environ["LC_ALL"] = "en.utf-8"

# os.environ["QMONITOR_BACKEND_LIB_PATH"] = "/var/QualcommProfiler/libs/backends/"
# os.environ["LD_LIBRARY_PATH"] = "$LD_LIBRARY_PATH:/var/QualcommProfiler/libs/"
# os.environ["PATH"] = "$PATH:/data/shared/QualcommProfiler/bins"

# Locks app version, prevents warnings
gi.require_version("Gdk", "3.0")
gi.require_version("Gst", "1.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gst, Gtk

# --- Graphing constants ---

UTIL_GRAPH_COLORS_RGBF = {
    CPU_UTIL_KEY: tuple(c / 255.0 for c in TRIA_PINK_RGBH),
    MEM_UTIL_KEY: tuple(c / 255.0 for c in TRIA_BLUE_RGBH),
    GPU_UTIL_KEY: tuple(c / 255.0 for c in TRIA_YELLOW_RGBH),
}

THERMAL_GRAPH_COLORS_RGBF = {
    CPU_THERMAL_KEY: tuple(c / 255.0 for c in TRIA_PINK_RGBH),
    MEM_THERMAL_KEY: tuple(c / 255.0 for c in TRIA_BLUE_RGBH),
    GPU_THERMAL_KEY: tuple(c / 255.0 for c in TRIA_YELLOW_RGBH),
}

UTIL_GRAPH_COLORS_RGBF = {
    CPU_UTIL_KEY: tuple(c / 255.0 for c in TRIA_PINK_RGBH),
    MEM_UTIL_KEY: tuple(c / 255.0 for c in TRIA_BLUE_RGBH),
    GPU_UTIL_KEY: tuple(c / 255.0 for c in TRIA_YELLOW_RGBH),
}

THERMAL_GRAPH_COLORS_RGBF = {
    CPU_THERMAL_KEY: tuple(c / 255.0 for c in TRIA_PINK_RGBH),
    MEM_THERMAL_KEY: tuple(c / 255.0 for c in TRIA_BLUE_RGBH),
    GPU_THERMAL_KEY: tuple(c / 255.0 for c in TRIA_YELLOW_RGBH),
}

GRAPH_LABEL_FONT_SIZE = 14
MAX_TIME_DISPLAYED = 0
MIN_TEMP_DISPLAYED = 35
MAX_TEMP_DISPLAYED = 95
MIN_UTIL_DISPLAYED = 0
MAX_UTIL_DISPLAYED = 100

# --- End Graphing constants ---

GladeBuilder = Gtk.Builder()
APP_FOLDER = os.path.dirname(__file__)
RESOURCE_FOLDER = os.path.join(APP_FOLDER, "resources")
LAYOUT_PATH = os.path.join(RESOURCE_FOLDER, "GSTLauncher.glade")

def get_min_time_delta_smoothed(time_series: list):
    """Returns the delta from the current time to the first entry in the time series. If the time series is empty, returns 0."""
    if not time_series: return 0

    x_min = -int(time.monotonic() - time_series[0])

    # Help with the jittering of the graph
    if abs(x_min - GRAPH_SAMPLE_WINDOW_SIZE_s) <= 1:
        x_min = -GRAPH_SAMPLE_WINDOW_SIZE_s

    return x_min

class VaiDemoManager:
    def __init__(self, port=7001):
        Gst.init(None)

        self.eventHandler = Handler()
        self.running = True
        self.demoSelection0Cnt = 0
        self.demoSelection1Cnt = 0
        self.demo0Interval = 0
        self.demo1Interval = 0
        self.demo0RunningIndex = 0
        self.demo1RunningIndex = 0

        GLib.timeout_add(1000, self.automateDemo)
        self.localApp()  # build all GTK widgets on the main thread

    # ADDITION: thread method to send telemetry via IOTCONNECT every 5 seconds
    def send_iotc_telemetry_loop(self):
        while not self.stop_event.is_set():
            try:
                self.eventHandler.update_sample_data()  # Explicit update
                sample_data = self.eventHandler.sample_data
                telemetry = {
                    "cpu_usage": sample_data.get(CPU_UTIL_KEY, 0),
                    "gpu_usage": sample_data.get(GPU_UTIL_KEY, 0),
                    "memory_usage": sample_data.get(MEM_UTIL_KEY, 0),
                    "cpu_temp": sample_data.get(CPU_THERMAL_KEY, 0),
                    "gpu_temp": sample_data.get(GPU_THERMAL_KEY, 0),
                    "memory_temp": sample_data.get(MEM_THERMAL_KEY, 0),
                    "critical": 85,  # example fixed value
                }
                self.iotc.send_telemetry(telemetry)
            except Exception as e:
                print(f"Telemetry sending error: {e}")
            time.sleep(5)

    # ADDITION: callback to handle incoming IOTCONNECT commands
    def handle_iotconnect_command(self, command):
        cmd_name = command.command_name
        print(f"[IOTCONNECT] Command received: {cmd_name}")

        # Default response setup
        ack_message = "Unknown command"
        ack_status = C2dAck.CMD_FAILED

        if cmd_name == 'start_demo':
            try:
                camera = command.command_args[0].lower()
                pipeline = command.command_args[1].lower()

                # Mapping clearly defined pipelines to their GUI indices
                pipeline_mapping = {
                    "1": 1,
                    "2": 2,
                    "3": 3,
                    "4": 4,
                    "5": 5,
                    "6": 6
                }

                pipeline_index = pipeline_mapping.get(pipeline)
                if pipeline_index is None:
                    raise ValueError(f"Invalid pipeline: {pipeline}")

                if camera == 'cam1':
                    GLib.idle_add(self.eventHandler.demo_selection0.set_active, pipeline_index)
                    ack_message = f"CAM1 started {pipeline}"
                    ack_status = C2dAck.CMD_SUCCESS_WITH_ACK
                elif camera == 'cam2':
                    GLib.idle_add(self.eventHandler.demo_selection1.set_active, pipeline_index)
                    ack_message = f"CAM2 started {pipeline}"
                    ack_status = C2dAck.CMD_SUCCESS_WITH_ACK
                else:
                    raise ValueError(f"Invalid camera: {camera}")

            except Exception as e:
                ack_message = f"Failed to start demo: {e}"
                ack_status = C2dAck.CMD_FAILED

            self.iotc.send_command_ack(command, ack_status, ack_message)

        elif cmd_name == 'stop_demo':
            try:
                camera = command.command_args[0].lower()

                if camera == 'cam1':
                    GLib.idle_add(self.eventHandler.demo_selection0.set_active, 0)  # 0 index stops the demo
                    ack_message = "CAM1 demo stopped"
                    ack_status = C2dAck.CMD_SUCCESS_WITH_ACK
                elif camera == 'cam2':
                    GLib.idle_add(self.eventHandler.demo_selection1.set_active, 0)
                    ack_message = "CAM2 demo stopped"
                    ack_status = C2dAck.CMD_SUCCESS_WITH_ACK
                else:
                    raise ValueError(f"Invalid camera: {camera}")

            except Exception as e:
                ack_message = f"Failed to stop demo: {e}"
                ack_status = C2dAck.CMD_FAILED

            self.iotc.send_command_ack(command, ack_status, ack_message)

        else:
            # Unknown command: still send an acknowledgment
            self.iotc.send_command_ack(command, ack_status, ack_message)

    def resize_graphs_dynamically(self, parent_widget, _allocation):
        """Resize graphing areas to be uniform and fill remaining space. To be called on size-allocate signal."""

        # Total width will be a function of the current lifecycle of the widget, it may have a surprising value
        total_width = parent_widget.get_allocated_width()
        total_height = parent_widget.get_allocated_height()
        self.main_window_dims = (total_width, total_height)
        if total_width == 0:
            return

        # These datagrid widths are what determine the remaining space
        data_grid = GladeBuilder.get_object("DataGrid")
        data_grid1 = GladeBuilder.get_object("DataGrid1")
        if not data_grid or not data_grid1:
            return

        remaining_graph_width = total_width - (
            data_grid.get_allocated_width() + data_grid1.get_allocated_width()
        )
        # Account for margins that arent included in the allocated width
        remaining_graph_width -= (
            data_grid.get_margin_start() + data_grid.get_margin_end()
        )
        remaining_graph_width -= (
            data_grid1.get_margin_start() + data_grid1.get_margin_end()
        )

        half = remaining_graph_width // 2
        if half < 0:
            return

        graph_top = self.eventHandler.GraphDrawAreaTop
        graph_bottom = self.eventHandler.GraphDrawAreaBottom
        # Only resize if changed, otherwise it can cause a loop
        if (
            graph_top.get_allocated_width() != half
            or graph_bottom.get_allocated_width() != half
        ):
            graph_top.set_size_request(half, -1)
            graph_bottom.set_size_request(half, -1)

    def init_graph_data(self, sample_size=GRAPH_SAMPLE_SIZE):
        """Initialize the graph data according to graph box size"""
        self.util_data = {
            TIME_KEY: collections.deque([], maxlen=sample_size),
            CPU_UTIL_KEY: collections.deque([], maxlen=sample_size),
            MEM_UTIL_KEY: collections.deque([], maxlen=sample_size),
            GPU_UTIL_KEY: collections.deque([], maxlen=sample_size),
        }
        self.thermal_data = {
            TIME_KEY: collections.deque([], maxlen=sample_size),
            CPU_THERMAL_KEY: collections.deque([], maxlen=sample_size),
            MEM_THERMAL_KEY: collections.deque([], maxlen=sample_size),
            GPU_THERMAL_KEY: collections.deque([], maxlen=sample_size),
        }

    def _sample_util_data(self):
        """Sample the utilization data; prefer this function because it timestamps entries to util data"""

        if self.util_data is None or self.thermal_data is None:
            self.init_graph_data()

        self.util_data[TIME_KEY].append(time.monotonic())

        # Sample and smooth the data with exponential smoothing
        cur_cpu = self.eventHandler.sample_data[CPU_UTIL_KEY]
        cur_gpu = self.eventHandler.sample_data[GPU_UTIL_KEY]
        cur_mem = self.eventHandler.sample_data[MEM_UTIL_KEY]

        last_cpu = self.util_data[CPU_UTIL_KEY][-1] if self.util_data[CPU_UTIL_KEY] else cur_cpu
        last_gpu = self.util_data[GPU_UTIL_KEY][-1] if self.util_data[GPU_UTIL_KEY] else cur_gpu
        last_mem = self.util_data[MEM_UTIL_KEY][-1] if self.util_data[MEM_UTIL_KEY] else cur_mem

        ema_cpu = get_ema(cur_cpu, last_cpu)
        ema_gpu = get_ema(cur_gpu, last_gpu)
        ema_mem = get_ema(cur_mem, last_mem)

        self.util_data[CPU_UTIL_KEY].append(ema_cpu)
        self.util_data[GPU_UTIL_KEY].append(ema_gpu)
        self.util_data[MEM_UTIL_KEY].append(ema_mem)

        cur_time = time.monotonic()
        while (
            self.util_data[TIME_KEY]
            and cur_time - self.util_data[TIME_KEY][0] > GRAPH_SAMPLE_WINDOW_SIZE_s
        ):
            self.util_data[TIME_KEY].popleft()
            self.util_data[CPU_UTIL_KEY].popleft()
            self.util_data[GPU_UTIL_KEY].popleft()
            self.util_data[MEM_UTIL_KEY].popleft()




    def on_util_graph_draw(self, widget, cr):
        """Draw the util graph on the draw area"""

        self._sample_util_data()

        width = widget.get_allocated_width()
        height = widget.get_allocated_height()

        draw_graph_background_and_border(
            width, height, cr, res_tuple=self.main_window_dims
        )

        x_min = get_min_time_delta_smoothed(self.util_data[TIME_KEY])

        x_lim = (x_min, MAX_TIME_DISPLAYED)
        y_lim = (MIN_UTIL_DISPLAYED, MAX_UTIL_DISPLAYED)

        x_axis, y_axis = draw_axes_and_labels(
            cr,
            width,
            height,
            x_lim,
            y_lim,
            x_ticks=4,
            y_ticks=2,
            dynamic_margin=True,
            x_label="seconds",
            y_label="%",
            res_tuple=self.main_window_dims,
        )
        draw_graph_data(
            self.util_data,
            UTIL_GRAPH_COLORS_RGBF,
            x_axis,
            y_axis,
            cr,
            y_lim=y_lim,
            res_tuple=self.main_window_dims,
        )

        self.eventHandler.GraphDrawAreaTop.queue_draw()

        return True

    def _sample_thermal_data(self):
        """Sample the thermal data; prefer this function because it timestamps entries to thermal data"""
        if self.thermal_data is None:
            self.init_graph_data()

        self.thermal_data[TIME_KEY].append(time.monotonic())

        # Sample and smooth the data with exponential smoothing
        cur_cpu = self.eventHandler.sample_data[CPU_THERMAL_KEY]
        cur_gpu = self.eventHandler.sample_data[GPU_THERMAL_KEY]
        cur_mem = self.eventHandler.sample_data[MEM_THERMAL_KEY]

        last_cpu = self.thermal_data[CPU_THERMAL_KEY][-1] if self.thermal_data[CPU_THERMAL_KEY] else cur_cpu
        last_gpu = self.thermal_data[GPU_THERMAL_KEY][-1] if self.thermal_data[GPU_THERMAL_KEY] else cur_gpu
        last_mem = self.thermal_data[MEM_THERMAL_KEY][-1] if self.thermal_data[MEM_THERMAL_KEY] else cur_mem

        ema_cpu = get_ema(cur_cpu, last_cpu)
        ema_gpu = get_ema(cur_gpu, last_gpu)
        ema_mem = get_ema(cur_mem, last_mem)

        self.thermal_data[CPU_THERMAL_KEY].append(
            ema_cpu
        )
        self.thermal_data[GPU_THERMAL_KEY].append(
            ema_gpu
        )
        self.thermal_data[MEM_THERMAL_KEY].append(
            ema_mem
        )

        cur_time = time.monotonic()
        while (
            self.thermal_data[TIME_KEY]
            and cur_time - self.thermal_data[TIME_KEY][0] > GRAPH_SAMPLE_WINDOW_SIZE_s
        ):
            self.thermal_data[TIME_KEY].popleft()
            self.thermal_data[CPU_THERMAL_KEY].popleft()
            self.thermal_data[GPU_THERMAL_KEY].popleft()
            self.thermal_data[MEM_THERMAL_KEY].popleft()

    def on_thermal_graph_draw(self, widget, cr):
        """Draw the graph on the draw area"""

        self._sample_thermal_data()

        width = widget.get_allocated_width()
        height = widget.get_allocated_height()

        draw_graph_background_and_border(
            width, height, cr, res_tuple=self.main_window_dims
        )
        x_min = get_min_time_delta_smoothed(self.thermal_data[TIME_KEY])
        x_lim = (x_min, MAX_TIME_DISPLAYED)
        y_lim = (MIN_TEMP_DISPLAYED, MAX_TEMP_DISPLAYED)

        x_axis, y_axis = draw_axes_and_labels(
            cr,
            width,
            height,
            x_lim,
            y_lim,
            x_ticks=4,
            y_ticks=2,
            dynamic_margin=True,
            x_label="seconds",
            y_label="°C",
            res_tuple=self.main_window_dims,
        )
        draw_graph_data(
            self.thermal_data,
            THERMAL_GRAPH_COLORS_RGBF,
            x_axis,
            y_axis,
            cr,
            y_lim=y_lim,
            res_tuple=self.main_window_dims,
        )

        self.eventHandler.GraphDrawAreaBottom.queue_draw()
        return True

    def automateDemo(self):
        if (self.eventHandler.CycleDemo0) and (self.demoSelection0Cnt > 0):
            cycleDemo0 = True
        else:
            cycleDemo0 = False
            self.demo0Interval = 0
            self.demo0RunningIndex = 1

        if (self.eventHandler.CycleDemo1) and (self.demoSelection1Cnt > 0):
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

                if self.eventHandler.dualDemoRunning1 != True:
                    self.eventHandler.demo_selection0.set_active(self.demo0RunningIndex)

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

                if self.eventHandler.dualDemoRunning0 != True:
                    self.eventHandler.demo_selection1.set_active(self.demo1RunningIndex)
            else:
                self.demo1Interval = self.demo1Interval + 1

        return GLib.SOURCE_CONTINUE

    def gui_data_update_loop(self):
        while not self.stop_event.is_set():
            try:
                self.eventHandler.update_sample_data()
            except Exception as e:
                print(f"GUI data update error: {e}")
            time.sleep(2)  # update every 2 seconds

    def localApp(self):
        global GladeBuilder

        GladeBuilder.add_from_file(LAYOUT_PATH)
        GladeBuilder.connect_signals(self.eventHandler)

        screen = Gdk.Screen.get_default()
        provider = Gtk.CssProvider()
        provider.load_from_path(os.path.join(RESOURCE_FOLDER, "app.css"))
        # ensure any previous instance of this CSS provider is removed before re-adding it
        Gtk.StyleContext.remove_provider_for_screen(screen, provider)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.eventHandler.MainWindow = GladeBuilder.get_object("mainWindow")
        self.eventHandler.MainWindow.connect("destroy", self.eventHandler.exit)
        self.eventHandler.MainWindow.connect(
            "size-allocate", self.resize_graphs_dynamically
        )
        self.eventHandler.aboutWindow = GladeBuilder.get_object("aboutWindow")
        self.eventHandler.FPSRate0 = GladeBuilder.get_object("FPS_rate_0")
        self.eventHandler.FPSRate1 = GladeBuilder.get_object("FPS_rate_1")
        self.eventHandler.CPU_load = GladeBuilder.get_object("CPU_load")
        self.eventHandler.GPU_load = GladeBuilder.get_object("GPU_load")
        self.eventHandler.MEM_load = GladeBuilder.get_object("MEM_load")
        self.eventHandler.CPU_temp = GladeBuilder.get_object("CPU_temp")
        self.eventHandler.GPU_temp = GladeBuilder.get_object("GPU_temp")
        self.eventHandler.MEM_temp = GladeBuilder.get_object("MEM_temp")
        self.eventHandler.TopBox = GladeBuilder.get_object("TopBox")
        self.eventHandler.DataGrid = GladeBuilder.get_object("DataGrid")
        self.eventHandler.BottomBox = GladeBuilder.get_object("BottomBox")
        self.eventHandler.DrawArea1 = GladeBuilder.get_object("DrawArea1")
        self.eventHandler.DrawArea2 = GladeBuilder.get_object("DrawArea2")
        self.eventHandler.GraphDrawAreaTop = GladeBuilder.get_object("GraphDrawAreaTop")
        self.eventHandler.GraphDrawAreaBottom = GladeBuilder.get_object("GraphDrawAreaBottom")
        self.eventHandler.demo_selection0 = GladeBuilder.get_object("demo_selection0")
        self.eventHandler.demo_selection1 = GladeBuilder.get_object("demo_selection1")

        model = self.eventHandler.demo_selection0.get_model()
        if model is not None:
            self.demoSelection0Cnt = len(model)

        model = self.eventHandler.demo_selection1.get_model()
        if model is not None:
            self.demoSelection1Cnt = len(model)

        # TODO: Dynamic sizing, positioning
        self.eventHandler.GraphDrawAreaTop.connect("draw", self.on_util_graph_draw)
        self.eventHandler.GraphDrawAreaBottom.connect(
            "draw", self.on_thermal_graph_draw
        )
        # Maybe keep canned generation for situations that perf depends arent available?
        self.util_data = None
        self.thermal_data = None

        self.eventHandler.QProf = QProfProcess()

        # TODO: Can just put these in CSS
        self.eventHandler.MainWindow.override_background_color(
            Gtk.StateFlags.NORMAL, Gdk.RGBA(23 / 255, 23 / 255, 23 / 255, 0)
        )
        self.eventHandler.TopBox.override_background_color(
            Gtk.StateType.NORMAL, Gdk.RGBA(23 / 255, 23 / 255, 23 / 255, 0.5)
        )

        self.eventHandler.BottomBox.override_background_color(
            Gtk.StateType.NORMAL, Gdk.RGBA(23 / 255, 23 / 255, 23 / 255, 0.8)
        )

        self.eventHandler.MainWindow.set_decorated(False)
        self.eventHandler.MainWindow.set_keep_below(True)
        self.eventHandler.MainWindow.maximize()


        self.eventHandler.QProf.start()

        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-cursor-theme-name","Yaru")
        settings.set_property("gtk-cursor-theme-size", 64)

        # ADDITION: IOTCONNECT Initialization
        try:
            device_config = DeviceConfig.from_iotc_device_config_json_file(
                device_config_json_path="iotc_config/iotcDeviceConfig.json",
                device_cert_path="iotc_config/device-cert.pem",
                device_pkey_path="iotc_config/device-pkey.pem"
            )
            self.iotc = Client(
                config=device_config,
                callbacks=Callbacks(command_cb=self.handle_iotconnect_command)
            )
            self.iotc.connect()
        except DeviceConfigError as dce:
            print("IOTCONNECT configuration error:", dce)
            sys.exit(1) # abort here if DeviceConfig fails, so the app doesn’t hang

        # ADDITION: create stop_event and launch telemetry + GUI update threads
        # Marking threads as daemons so Python won't wait to shut down for sys.exit(…)
        self.stop_event = threading.Event()
        threading.Thread(target=self.send_iotc_telemetry_loop, daemon=True).start()
        threading.Thread(target=self.gui_data_update_loop, daemon=True).start()

        # Finally show the window and enter GTK mainloop:
        self.eventHandler.MainWindow.show_all()

        # Gtk.main() was removed from here so that threads (telemetry, GUI-update, etc.)
        # can be started first without blocking. Instead, call Gtk.main() in the
        # `if __name__ == "__main__":` block to allow initialization of IOTCONNECT
        # and background threads before entering the GTK event loop.

if __name__ == "__main__":
    print(TRIA)
    print(f"\nLaunching {APP_HEADER}")
    # Create the video object
    # Add port= if is necessary to use a different one
    video = VaiDemoManager()
    try:
        Gtk.main()
    except KeyboardInterrupt:
        print("Exiting QCS6490 Vision AI due to SIGINT")
        video.stop_event.set()
        Gtk.main_quit()
        sys.exit(0) # ensure process fully terminates after GTK/main threads stop