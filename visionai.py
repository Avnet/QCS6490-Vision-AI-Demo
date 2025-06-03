#!/usr/bin/env python3

import collections
import os
import threading
import time

import gi

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
        self.localAppThread = threading.Thread(target=self.localApp)
        self.localAppThread.start()

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

    def localApp(self):
        global GladeBuilder

        GladeBuilder.add_from_file(LAYOUT_PATH)
        GladeBuilder.connect_signals(self.eventHandler)

        screen = Gdk.Screen.get_default()
        provider = Gtk.CssProvider()
        provider.load_from_path(os.path.join(RESOURCE_FOLDER, "app.css"))
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
        self.eventHandler.DSP_load = GladeBuilder.get_object("DSP_load")
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
        self.eventHandler.MainWindow.show_all()

        self.eventHandler.QProf.start()

        settings = Gtk.Settings.get_default()
        settings.set_property("gtk-cursor-theme-name","Yaru")
        settings.set_property("gtk-cursor-theme-size", 32)

        Gtk.main()


if __name__ == "__main__":
    print(TRIA)
    print(f"\nLaunching {APP_HEADER}")
    # Create the video object
    # Add port= if is necessary to use a different one
    video = VaiDemoManager()
