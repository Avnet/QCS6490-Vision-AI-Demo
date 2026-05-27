import gi
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk

class MonitorDetector:
    @staticmethod
    def is_monitor_above_2k():
        """
        Gets the resolution of all connected monitors using GTK.
        This method is compatible with both Wayland and X11.

        Returns:
            returns True if a monitor has a resolution above 2K.
        """
        print('getting resolution')
        above_2k = False
        resolutions = []
        # Gdk.Display.get_default() will correctly connect to
        # the running display server (Wayland or X11).
        display = Gdk.Display.get_default()
        if not display:
            print("Could not get default display.")
        else:
            num_monitors = display.get_n_monitors()
            print("monitor count:", num_monitors)
            for i in range(num_monitors):
                monitor = display.get_monitor(i)
                if monitor:
                    geometry = monitor.get_geometry()
                    # The geometry gives the current resolution of the monitor.
                    resolutions.append((geometry.width, geometry.height))
                    print("width:", geometry.width, " height:", geometry.height)
                    # Check if resolution is greater than 2K (2560x1440)
                    if geometry.width > 2560 or geometry.height > 1440:
                        # Confirm it's a valid resolution
                        if geometry.width >= 3840 or geometry.height >= 2160:
                            above_2k = True
                            print("found a monitor with resolution 2K or greater")
                            break  # Found a 2K or higher display

        return above_2k
