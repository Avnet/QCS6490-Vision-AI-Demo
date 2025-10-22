#!/usr/bin/env python3

import collections
import os
import sys
import threading
import time
import gi

from vai.common import (APP_HEADER, CPU_THERMAL_KEY, CPU_UTIL_KEY,
                        GPU_THERMAL_KEY, GPU_UTIL_KEY, GRAPH_SAMPLE_SIZE,
                        MEM_THERMAL_KEY, MEM_UTIL_KEY, DSP_UTIL_KEY, TIME_KEY, 
                        TRIA, TRIA_BLUE_RGBH, TRIA_PINK_RGBH, TRIA_YELLOW_RGBH, 
                        TRIA_GREEN_RGBH, GRAPH_SAMPLE_WINDOW_SIZE_s,
                        get_ema)
from vai.graphing import (draw_axes_and_labels,
                          draw_graph_background_and_border, draw_graph_data)
from vai.handler import Handler
from vai.qprofile import QProfProcess

class FdFilter:
    """
    Redirects low-level file descriptors (stdout, stderr) to a pipe,
    filters the output in a separate thread, and writes the filtered
    output back to the original destination. This is necessary to
    suppress messages from C libraries that write directly to file
    descriptors, bypassing sys.stdout/sys.stderr.
    """
    def __init__(self, filter_strings):
        self.filter_strings = [s.lower() for s in filter_strings]
        self.original_stdout_fd = os.dup(1)
        self.original_stderr_fd = os.dup(2)

        # Create pipes to intercept stdout and stderr
        self.stdout_pipe_r, self.stdout_pipe_w = os.pipe()
        self.stderr_pipe_r, self.stderr_pipe_w = os.pipe()

        # Redirect stdout and stderr to the write-ends of the pipes
        os.dup2(self.stdout_pipe_w, 1)
        os.dup2(self.stderr_pipe_w, 2)

        # Create threads to read from the pipes, filter, and write to original FDs
        self.stdout_thread = threading.Thread(target=self._pipe_reader, args=(self.stdout_pipe_r, self.original_stdout_fd))
        self.stderr_thread = threading.Thread(target=self._pipe_reader, args=(self.stderr_pipe_r, self.original_stderr_fd))
        self.stdout_thread.daemon = True
        self.stderr_thread.daemon = True
        self.stdout_thread.start()
        self.stderr_thread.start()

    def _pipe_reader(self, pipe_r_fd, original_dest_fd):
        """Reads from a pipe, filters, and writes to the destination."""
        with os.fdopen(pipe_r_fd, 'r') as pipe_file:
            for line in iter(pipe_file.readline, ''):
                if not any(f in line.lower() for f in self.filter_strings):
                    os.write(original_dest_fd, line.encode('utf-8'))

# Locks app version, prevents warnings
gi.require_version("Gdk", "3.0")
gi.require_version("Gst", "1.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gst, Gtk

# --- Graphing constants ---

UTIL_GRAPH_COLORS_RGBF = {
    CPU_UTIL_KEY: tuple(c / 255.0 for c in TRIA_PINK_RGBH),
    MEM_UTIL_KEY: tuple(c / 255.0 for c in TRIA_BLUE_RGBH),
    GPU_UTIL_KEY: tuple(c / 255.0 for c in TRIA_YELLOW_RGBH),
    DSP_UTIL_KEY: tuple(c / 255.0 for c in TRIA_GREEN_RGBH),
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
def is_monitor_above_2k():
    """
    Checks if any connected monitor has a native resolution greater than 2K (2560x1440).
    Uses EDID data from /sys/class/drm/ to determine resolution.
    
    Returns:
        bool: True if any monitor has resolution > 2560x1440, False otherwise.
    """
    drm_path = '/sys/class/drm/'
    above_2k = False

    try:
        for device in os.listdir(drm_path):
            # Look for connected display devices (e.g., card0-HDMI-A-1, card0-eDP-1)
            if not device.startswith('card'):
                continue

            status_file = os.path.join(drm_path, device, 'status')
            edid_file = os.path.join(drm_path, device, 'edid')

            # Only check if the monitor is connected
            if os.path.exists(status_file) and os.path.exists(edid_file):
                with open(status_file, 'r') as f:
                    if f.read().strip() != 'connected':
                        continue

                # Read EDID data
                with open(edid_file, 'rb') as f:
                    edid_data = f.read()

                if len(edid_data) < 128:
                    continue  # Invalid EDID

                # Parse EDID to get the native resolution
                # Detailed Timing Descriptor 1 starts at 54th byte
                dtd_start = 54
                if dtd_start + 18 <= len(edid_data):
                    # First DTD (usually the preferred/native mode)
                    dtd = edid_data[dtd_start:dtd_start+18]

                    # Parse horizontal active pixels (bytes 2-3)
                    h_active_lo = dtd[2]
                    h_active_hi = (dtd[4] & 0xF0) >> 4
                    width = h_active_lo + (h_active_hi << 8)

                    # Parse vertical active lines (bytes 5-6)
                    v_active_lo = dtd[5]
                    v_active_hi = (dtd[7] & 0xF0) >> 4
                    height = v_active_lo + (v_active_hi << 8)

                    # Check if resolution is greater than 2K (2560x1440)
                    if width > 2560 or height > 1440:
                        # Confirm it's a valid resolution
                        if width >= 3840 or height >= 2160:
                            above_2k = True
                            break  # Found a 4K or higher display

    except Exception as e:
        print(f"Error reading EDID: {e}")
        return False

    return above_2k

GladeBuilder = Gtk.Builder()
APP_FOLDER = os.path.dirname(__file__)

if is_monitor_above_2k():
    print("Connected monitor resolution is above 2K (e.g., 4K).")
    RESOURCE_FOLDER = os.path.join(APP_FOLDER, "resources_high")
else:
    print("No monitor above 2K resolution detected.")
    RESOURCE_FOLDER = os.path.join(APP_FOLDER, "resources_low")

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
        self.eventHandler = Handler()
        self.running = True
        self.demo0Interval = 0
        self.demo1Interval = 0
        self.demo0RunningIndex = 0
        self.demo1RunningIndex = 0

    def resize_graphs_dynamically(self, parent_widget, _allocation):
        if not self.eventHandler.GraphDrawAreaTop or not self.eventHandler.GraphDrawAreaBottom:
            return
        
        """Resize graphing areas to be uniform and fill remaining space. To be called on size-allocate signal."""

        # Total width will be a function of the current lifecycle of the widget, it may have a surprising value
        total_width = parent_widget.get_allocated_width()
        total_height = parent_widget.get_allocated_height()

        self.main_window_dims = (total_width, total_height)
        if total_width == 0:
            return

        BottomBox = GladeBuilder.get_object("BottomBox")
        if not BottomBox:
            return

        BottomBox_width = BottomBox.get_allocated_width()
        if BottomBox_width == 0:
            return        

        # These datagrid widths are what determine the remaining space
        data_grid = GladeBuilder.get_object("DataGrid")
        data_grid1 = GladeBuilder.get_object("DataGrid1")
        if not data_grid or not data_grid1:
            return

        remaining_graph_width = BottomBox_width - (
            data_grid.get_allocated_width() + data_grid1.get_allocated_width()
        )
        # Account for margins that arent included in the allocated width
        remaining_graph_width -= (
            data_grid.get_margin_start() + data_grid.get_margin_end() + 10
        )
        remaining_graph_width -= (
            data_grid1.get_margin_start() + data_grid1.get_margin_end() + 10
        )

        half = remaining_graph_width // 2
        if half < 0:
            return

        try:
            window_x, window_y = self.eventHandler.DrawArea1.translate_coordinates(self.eventHandler.DrawArea1.get_toplevel(), 0, 0)

            camera_bottom_position = window_y + self.eventHandler.DrawArea1.get_allocated_height()

            if camera_bottom_position > 148:
                BottomBox.set_size_request(-1, round(total_height - camera_bottom_position))
        except:
            pass

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
            DSP_UTIL_KEY: collections.deque([], maxlen=sample_size),
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
        cur_dsp = self.eventHandler.sample_data[DSP_UTIL_KEY]

        last_cpu = self.util_data[CPU_UTIL_KEY][-1] if self.util_data[CPU_UTIL_KEY] else cur_cpu
        last_gpu = self.util_data[GPU_UTIL_KEY][-1] if self.util_data[GPU_UTIL_KEY] else cur_gpu
        last_mem = self.util_data[MEM_UTIL_KEY][-1] if self.util_data[MEM_UTIL_KEY] else cur_mem
        last_dsp = self.util_data[DSP_UTIL_KEY][-1] if self.util_data[DSP_UTIL_KEY] else cur_dsp

        ema_cpu = get_ema(cur_cpu, last_cpu)
        ema_gpu = get_ema(cur_gpu, last_gpu)
        ema_mem = get_ema(cur_mem, last_mem)
        ema_dsp = get_ema(cur_dsp, last_dsp)

        self.util_data[CPU_UTIL_KEY].append(ema_cpu)
        self.util_data[GPU_UTIL_KEY].append(ema_gpu)
        self.util_data[MEM_UTIL_KEY].append(ema_mem)
        self.util_data[DSP_UTIL_KEY].append(ema_dsp)

        cur_time = time.monotonic()
        while (
            self.util_data[TIME_KEY]
            and cur_time - self.util_data[TIME_KEY][0] > GRAPH_SAMPLE_WINDOW_SIZE_s
        ):
            self.util_data[TIME_KEY].popleft()
            self.util_data[CPU_UTIL_KEY].popleft()
            self.util_data[GPU_UTIL_KEY].popleft()
            self.util_data[MEM_UTIL_KEY].popleft()
            self.util_data[DSP_UTIL_KEY].popleft()

    def on_util_graph_draw(self, widget, cr):
        if not self.eventHandler.GraphDrawAreaTop:
            return True

        if not self.util_data:
            self.eventHandler.GraphDrawAreaTop.queue_draw()
            return True
        
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
        if not self.eventHandler.GraphDrawAreaBottom:
            return
        
        if not self.thermal_data:
            self.eventHandler.GraphDrawAreaBottom.queue_draw()
            return True    
            
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

    def localApp(self):
        global GladeBuilder

        # Initialize GStreamer. The log level is now controlled by the GST_DEBUG environment variable.
        Gst.init(None)

        self.init_graph_data()

        """Build application window and connect signals"""
        GladeBuilder.add_from_file(LAYOUT_PATH)
        GladeBuilder.connect_signals(self.eventHandler)

        screen = Gdk.Screen.get_default()
        provider = Gtk.CssProvider()
        provider.load_from_path(os.path.join(RESOURCE_FOLDER, "app.css"))
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.eventHandler.MainWindow = GladeBuilder.get_object("mainWindow")
        self.eventHandler.MainWindow.connect(
            "size-allocate", self.resize_graphs_dynamically
        )
        self.eventHandler.aboutWindow = GladeBuilder.get_object("aboutWindow")
        self.eventHandler.FPSRate0 = GladeBuilder.get_object("FPS_rate_0")
        self.eventHandler.FPSRate1 = GladeBuilder.get_object("FPS_rate_1")
        self.eventHandler.CPU_load = GladeBuilder.get_object("CPU_load")
        self.eventHandler.GPU_load = GladeBuilder.get_object("GPU_load")
        self.eventHandler.DSP_load = GladeBuilder.get_object("DSP_load")
        self.eventHandler.MEM_load = GladeBuilder.get_object("MEM_load")
        self.eventHandler.CPU_temp = GladeBuilder.get_object("CPU_temp")
        self.eventHandler.GPU_temp = GladeBuilder.get_object("GPU_temp")
        self.eventHandler.MEM_temp = GladeBuilder.get_object("MEM_temp")
        self.eventHandler.TopBox = GladeBuilder.get_object("TopBox")
        self.eventHandler.DataGrid = GladeBuilder.get_object("DataGrid")
        self.eventHandler.BottomBox = GladeBuilder.get_object("BottomBox")
        self.eventHandler.DrawArea1 = GladeBuilder.get_object("videosink0")
        self.eventHandler.DrawArea2 = GladeBuilder.get_object("videosink1")
        self.eventHandler.set_video_sink(0, GladeBuilder.get_object("videosink0"))
        self.eventHandler.set_video_sink(1, GladeBuilder.get_object("videosink1"))
        self.eventHandler.GraphDrawAreaTop = GladeBuilder.get_object("GraphDrawAreaTop")
        self.eventHandler.GraphDrawAreaBottom = GladeBuilder.get_object("GraphDrawAreaBottom")
        self.eventHandler.demo_selection0 = GladeBuilder.get_object("demo_selection0")
        self.eventHandler.demo_selection1 = GladeBuilder.get_object("demo_selection1")
        self.eventHandler.dialogWindow = GladeBuilder.get_object("dialogWindow")
        
        """Disbale pipeline selection until cameras are found """
        self.eventHandler.demo_selection0.set_sensitive(False)
        self.eventHandler.demo_selection1.set_sensitive(False)

        model = self.eventHandler.demo_selection0.get_model()
        if model is not None:
            self.eventHandler.demoSelection0Cnt = len(model)

        model = self.eventHandler.demo_selection1.get_model()
        if model is not None:
            self.eventHandler.demoSelection1Cnt = len(model)

        # TODO: Dynamic sizing, positioning
        self.eventHandler.GraphDrawAreaTop.connect("draw", self.on_util_graph_draw)
        self.eventHandler.GraphDrawAreaBottom.connect("draw", self.on_thermal_graph_draw)

        self.eventHandler.QProf = QProfProcess()
        self.eventHandler.QProf.daemon = True # Ensure thread doesn't block app exit

        # TODO: Can just put these in CSS
        self.eventHandler.MainWindow.override_background_color(
            Gtk.StateFlags.NORMAL, Gdk.RGBA(23 / 255, 23 / 255, 23 / 255, 0)
        )
        self.eventHandler.TopBox.override_background_color(
            Gtk.StateType.NORMAL, Gdk.RGBA(23 / 255, 23 / 255, 23 / 255, 0.5)
        )

        self.eventHandler.BottomBox.override_background_color(
            Gtk.StateType.NORMAL, Gdk.RGBA(0 / 255, 23 / 255, 23 / 255, 1)
        )

        self.eventHandler.MainWindow.set_decorated(False)
        self.eventHandler.MainWindow.set_keep_below(True)
        self.eventHandler.MainWindow.maximize()
        self.eventHandler.MainWindow.show_all()


        self.eventHandler.QProf.start()

        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-cursor-theme-name","Adwaita")
        settings.set_property("gtk-cursor-theme-size", 32)

        # --- Filter unwanted log messages from ML plugin ---
        # The QNN plugin prints log messages that can't be suppressed via
        # environment variables, so we filter them from the low-level
        # file descriptors directly.
        filter_list = [
            "<W> No usable logger handle was found",
            "<W> Logs will be sent to the system's default channel",
            "Could not find ncvt for conv cost",
            "Could not find conv_ctrl for conv cost"
        ]
        self.log_filter = FdFilter(filter_list)
        # --- End Filter ---

        Gtk.main()

if __name__ == "__main__":
    print(TRIA)
    print(f"\nLaunching {APP_HEADER}")
    # Create the video object
    # Add port= if is necessary to use a different one
    video = VaiDemoManager()
    video.localApp()
