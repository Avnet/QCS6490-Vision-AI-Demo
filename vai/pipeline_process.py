import os
#os.environ["GST_DEBUG"] = "3"
import queue as q_lib
import numpy as np
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
from vai.message_filter import FdFilter


def _resize_bgra(img, h, w):
    """Nearest-neighbour resize to (h, w) without external libraries."""
    oh, ow = img.shape[:2]
    if (oh, ow) == (h, w):
        return img
    yi = (np.arange(h) * oh / h).astype(np.int32)
    xi = (np.arange(w) * ow / w).astype(np.int32)
    return img[np.ix_(yi, xi)]


def _alpha_composite(cam_bgra, overlay_bgra, ml_alpha):
    """Alpha-blend ML overlay onto camera frame, return RGB (H×W×3 uint8)."""
    h, w = cam_bgra.shape[:2]
    overlay_bgra = _resize_bgra(overlay_bgra, h, w)
    cam_rgb     = cam_bgra[:, :, 2::-1].astype(np.float32)
    overlay_rgb = overlay_bgra[:, :, 2::-1].astype(np.float32)
    alpha       = (overlay_bgra[:, :, 3:4].astype(np.float32) / 255.0) * ml_alpha
    return np.ascontiguousarray(
        (cam_rgb * (1.0 - alpha) + overlay_rgb * alpha).astype(np.uint8)
    )


def _stack_vertical(cam_bgra, depth_bgra):
    """Stack camera (top) and depth map (bottom), return RGB (2H×W×3 uint8)."""
    h, w = cam_bgra.shape[:2]
    depth_bgra = _resize_bgra(depth_bgra, h, w)
    return np.ascontiguousarray(
        np.vstack([cam_bgra[:, :, 2::-1], depth_bgra[:, :, 2::-1]])
    )


def gstreamer_process(pipeline_description, queue, stop_event):
    Gst.init(None)

    filter_list = [
        "<W> No usable logger handle was found",
        "<W> Logs will be sent to the system's default channel",
        "Could not find ncvt for conv cost",
        "Could not find conv_ctrl for conv cost",
        "[2] concat.cc:1"
    ]
    FdFilter(filter_list)

    pipeline = Gst.parse_launch(pipeline_description)

    appsink = pipeline.get_by_name('videosink')
    mlsink  = pipeline.get_by_name('mlsink')   # None for CAMERA demo

    # Depth segmentation stacks camera and depth vertically (2 separate views).
    # Semantic segmentation blends the class-colour mask at 50% alpha.
    # All other ML demos overlay sparse annotations at full alpha.
    depth_stack = 'midas' in pipeline_description
    ml_alpha    = 0.5 if 'deeplab' in pipeline_description else 1.0

    # Shared latest ML overlay frame; Python GIL makes reference replacement atomic.
    latest_ml = [None]

    def on_cam_sample(sink):
        sample = sink.emit('pull-sample')
        if sample is None:
            return Gst.FlowReturn.OK
        buf  = sample.get_buffer()
        caps = sample.get_caps()
        try:
            h = caps.get_structure(0).get_value('height')
            w = caps.get_structure(0).get_value('width')
            buf_data = buf.extract_dup(0, buf.get_size())
            if len(buf_data) != h * w * 4:
                return Gst.FlowReturn.OK
            cam_bgra = np.ndarray((h, w, 4), buffer=buf_data, dtype=np.uint8)
            overlay = latest_ml[0]
            if overlay is not None:
                if depth_stack:
                    arr = _stack_vertical(cam_bgra, overlay)
                else:
                    arr = _alpha_composite(cam_bgra, overlay, ml_alpha)
            else:
                arr = np.ascontiguousarray(cam_bgra[:, :, 2::-1])
            try:
                queue.put_nowait(arr)
            except q_lib.Full:
                pass
        finally:
            return Gst.FlowReturn.OK

    def on_ml_sample(sink):
        sample = sink.emit('pull-sample')
        if sample is None:
            return Gst.FlowReturn.OK
        buf  = sample.get_buffer()
        caps = sample.get_caps()
        try:
            h = caps.get_structure(0).get_value('height')
            w = caps.get_structure(0).get_value('width')
            buf_data = buf.extract_dup(0, buf.get_size())
            if len(buf_data) == h * w * 4:
                latest_ml[0] = np.ndarray((h, w, 4),
                                          buffer=buf_data,
                                          dtype=np.uint8).copy()
        finally:
            return Gst.FlowReturn.OK

    appsink.connect('new-sample', on_cam_sample)
    if mlsink:
        mlsink.connect('new-sample', on_ml_sample)

    pipeline.set_state(Gst.State.PLAYING)

    loop = GLib.MainLoop()

    def on_pipeline_message(bus, message):
        if message.type == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"Pipeline error: {err.message} | {debug}")
        elif message.type == Gst.MessageType.EOS:
            src_name = message.src.get_name() if message.src else "unknown"
            print(f"Pipeline EOS received from: {src_name}")
        if appsink:
            appsink.set_property("emit-signals", False)
        if mlsink:
            mlsink.set_property("emit-signals", False)
        if loop.is_running():
            loop.quit()

    def check_stop_event():
        if stop_event.is_set():
            print("External stop event received, shutting down pipeline...")
            if appsink:
                appsink.set_property("emit-signals", False)
            if mlsink:
                mlsink.set_property("emit-signals", False)
            if loop.is_running():
                loop.quit()
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    GLib.timeout_add(100, check_stop_event)

    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message::eos", on_pipeline_message)
    bus.connect("message::error", on_pipeline_message)

    try:
        loop.run()
    except Exception as e:
        print(f"GStreamer process encountered an error: {e}")
    finally:
        bus.remove_signal_watch()

        if appsink:
            appsink.set_property("emit-signals", False)
        if mlsink:
            mlsink.set_property("emit-signals", False)

        print("Transitioning pipeline to NULL...")
        pipeline.set_state(Gst.State.NULL)
        ret, _, _ = pipeline.get_state(8 * Gst.SECOND)
        if ret != Gst.StateChangeReturn.SUCCESS:
            print(f"Warning: pipeline did not reach NULL within timeout "
                  f"(result: {ret.value_nick}). ISP resources may not be fully released.")

        queue.close()
        queue.cancel_join_thread()

        Gst.deinit()
