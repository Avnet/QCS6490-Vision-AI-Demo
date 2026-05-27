import queue as q_lib
import numpy as np
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
from vai.message_filter import FdFilter

def gstreamer_process(pipeline_description, queue, stop_event):
    # Initialize GStreamer in the child process
    Gst.init(None)
    

    # --- Filter unwanted log messages from ML plugin ---
    # The QNN plugin prints log messages that can't be suppressed via
    # environment variables, so we filter them from the low-level
    # file descriptors directly.
    filter_list = [
        "<W> No usable logger handle was found",
        "<W> Logs will be sent to the system's default channel",
        "Could not find ncvt for conv cost",
        "Could not find conv_ctrl for conv cost",
        "[2] concat.cc:1"
    ]
    FdFilter(filter_list)
    # --- End Filter ---


    # Create the pipeline
    pipeline = Gst.parse_launch(pipeline_description)
    
    appsink = pipeline.get_by_name('videosink')
    
    def on_new_sample(sink):
        sample = sink.emit('pull-sample')
        buf = sample.get_buffer()
        caps = sample.get_caps()
        try:
            arr = np.ndarray(
                (caps.get_structure(0).get_value('height'),
                caps.get_structure(0).get_value('width'), 3),
                buffer=buf.extract_dup(0, buf.get_size()),
                dtype=np.uint8
            )
            try:
                # Use put_nowait to avoid hanging the GStreamer thread
                queue.put_nowait(arr)
            except q_lib.Full:
                pass
        finally:
            return Gst.FlowReturn.OK

    appsink.connect('new-sample', on_new_sample)
    pipeline.set_state(Gst.State.PLAYING)
    
    loop = GLib.MainLoop()
    
    def stop_pipeline(bus, message):
        # 1. Disable the appsink to stop feeding the queue
        if appsink:
            appsink.set_property("emit-signals", False)
        
        # 2. Transition to NULL state and wait for completion
        print(f"Received {Gst.message_type_get_name(message.type)}: transitioning to NULL...")
        pipeline.set_state(Gst.State.NULL)
        
        # Wait indefinitely for the state change to complete (crucial for hardware release)
        pipeline.get_state(Gst.CLOCK_TIME_NONE)
        
        # 3. Signal the loop to quit.
        if loop.is_running():
            loop.quit()
    
    # This is the secret: periodically check the event from WITHIN the GLib loop
    def check_stop_event():
        if stop_event.is_set():
            print("External stop event: Sending EOS to pipeline...")
            # Force EOS on the pipeline. The bus message will trigger stop_pipeline.
            if not pipeline.send_event(Gst.Event.new_eos()):
                print("Warning: Failed to send EOS, forcing loop exit.")
                loop.quit()
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    GLib.timeout_add(100, check_stop_event)

    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message::eos", stop_pipeline)
    bus.connect("message::error", stop_pipeline)
    
    try:
        loop.run()
    except Exception as e:
        print(f"GStreamer process encountered an error: {e}")
    finally:
        # Ensure cleanup happens even if loop.run() is interrupted
        print("Setting pipeline to NULL state...")
        pipeline.set_state(Gst.State.NULL)
        
        # Clear the bus to prevent messages arriving during/after cleanup
        bus.remove_signal_watch()

        queue.close()
        queue.cancel_join_thread()

        Gst.deinit()
