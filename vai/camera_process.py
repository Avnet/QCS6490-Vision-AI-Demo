import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
from vai.message_filter import FdFilter


def camera_capture_process(source_pipeline, socket_path, stop_event):
    """
    Persistent camera capture process.

    Keeps qtiqmmfsrc / v4l2src alive across ML demo switches. Frames are
    forwarded as DMA-BUF file descriptors via qtisocketsink. The consumer
    pipeline asserts compression=ubwc in the capsfilter after qtisocketsrc so
    hardware elements (qtimlvconverter, qtivtransform) take the hardware path.

    source_pipeline : GStreamer source string ending with a caps filter
    socket_path     : Unix domain socket path, e.g. '/tmp/vai_cam0.sock'
    stop_event      : mp.Event; set only on application exit
    """
    import os
    print(f"[CamProcess] started pid={os.getpid()}: {source_pipeline}", flush=True)

    Gst.init(None)

    FdFilter([
        "<W> No usable logger handle was found",
        "<W> Logs will be sent to the system's default channel",
        "dummy call to rpcmem_init",
    ])

    pipeline_desc = f"{source_pipeline} ! qtisocketsink socket={socket_path} sync=false"
    print(f"[CamProcess] pipeline: {pipeline_desc}", flush=True)
    pipeline = Gst.parse_launch(pipeline_desc)

    ret = pipeline.set_state(Gst.State.PLAYING)
    print(f"[CamProcess] set_state(PLAYING) -> {ret.value_nick}", flush=True)

    loop = GLib.MainLoop()

    def on_camera_message(bus, message):
        if message.type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"[CamProcess] error: {err.message} | {debug}", flush=True)
        else:
            print("[CamProcess] unexpected EOS.", flush=True)
        if loop.is_running():
            loop.quit()

    def check_stop():
        if stop_event.is_set():
            print("[CamProcess] stopping...", flush=True)
            if loop.is_running():
                loop.quit()
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def report_state():
        _, state, _ = pipeline.get_state(0)
        print(f"[CamProcess] state @ 5 s: {state.value_nick}", flush=True)
        return GLib.SOURCE_REMOVE

    GLib.timeout_add(5000, report_state)
    GLib.timeout_add(100, check_stop)
    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message::error", on_camera_message)
    bus.connect("message::eos", on_camera_message)

    try:
        loop.run()
    except Exception as e:
        print(f"[CamProcess] exception: {e}", flush=True)
    finally:
        bus.remove_signal_watch()
        print("[CamProcess] transitioning to NULL...", flush=True)
        pipeline.set_state(Gst.State.NULL)
        ret, _, _ = pipeline.get_state(10 * Gst.SECOND)
        if ret != Gst.StateChangeReturn.SUCCESS:
            print(f"[CamProcess] NULL timed out ({ret.value_nick}).", flush=True)
        Gst.deinit()
