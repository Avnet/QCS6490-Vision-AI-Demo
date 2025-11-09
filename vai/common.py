"""Common utilities and constants for VAI demo"""

import subprocess

GRAPH_SAMPLE_WINDOW_SIZE_s = 31
HW_SAMPLING_PERIOD_ms = 250
GRAPH_DRAW_PERIOD_ms = 30
AUTOMATIC_DEMO_SWITCH_s = 60
QUIT_CLEANUP_DELAY_ms = 1000

GRAPH_SAMPLE_SIZE = int(GRAPH_SAMPLE_WINDOW_SIZE_s * 1000 / GRAPH_DRAW_PERIOD_ms)

TIME_KEY = "time"
CPU_UTIL_KEY = "cpu %"
MEM_UTIL_KEY = "lpddr5 %"
GPU_UTIL_KEY = "gpu %"
DSP_UTIL_KEY = "dsp %"
CPU_THERMAL_KEY = "cpu temp (°c)"
MEM_THERMAL_KEY = "lpddr5 temp (°c)"
GPU_THERMAL_KEY = "gpu temp (°c)"

# Triadic colors, indexed on Tria pink
TRIA_PINK_RGBH = (0xFE, 0x00, 0xA2)
TRIA_BLUE_RGBH = (0x00, 0xA2, 0xFE)
TRIA_YELLOW_RGBH = (0xFE, 0xDB, 0x00)
TRIA_GREEN_RGBH = (0x22, 0xB1, 0x4C)

# WARN: These commands will be processed by application. Tags like <TAG> are likely placeholder

# Having one default is fine, as we can extrapolate for the other window
DEFAULT_SINK = 'gtksink name="videosink" sync=false'

QUEUE_LITE = 'queue max-size-buffers=1 leaky=downstream'
USB_CAM_CAPS = ' ! qtivtransform ! video/x-raw,format=RGB,width=640,height=480,framerate=30/1'
MIPI_CAM_CAPS = ' ! video/x-raw,format=NV12_Q08C,width=640,height=480,framerate=30/1'


CAMERA = f'<DATA_SRC> ! {QUEUE_LITE} ! qtivcomposer name=mixer ! <DISPLAY_SINK>'

POSE_DETECTION = f'<DATA_SRC> ! tee name=split \
split. ! {QUEUE_LITE} ! qtivcomposer name=mixer ! <DISPLAY_SINK> \
split. ! {QUEUE_LITE} ! qtimlvconverter ! {QUEUE_LITE} ! qtimltflite delegate=external external-delegate-path=libQnnTFLiteDelegate.so \
external-delegate-options="QNNExternalDelegate,backend_type=htp;" model=/etc/models/hrnet_pose_quantized.tflite ! {QUEUE_LITE} ! \
qtimlpostprocess results=2 module=hrnet labels=/etc/labels/hrnet_pose.json settings=/etc/labels/hrnet_settings.json ! \
qtivtransform ! video/x-raw,format=BGRA,width=640,height=360 ! {QUEUE_LITE} ! mixer.'

CLASSIFICATION = f'<DATA_SRC> ! tee name=split \
split. ! {QUEUE_LITE} ! qtivcomposer name=mixer sink_1::position="<30, 30>" sink_1::dimensions="<480, 480>" ! {QUEUE_LITE} ! <DISPLAY_SINK> \
split. ! {QUEUE_LITE} ! qtimlvconverter ! {QUEUE_LITE} ! qtimltflite delegate=external external-delegate-path=libQnnTFLiteDelegate.so \
external-delegate-options="QNNExternalDelegate,backend_type=htp;" model=/etc/models/inception_v3_quantized.tflite ! {QUEUE_LITE} ! \
qtimlpostprocess settings="{{\\"confidence\\": 40.0}}" results=2 module=mobilenet-softmax labels=/etc/labels/classification.json ! \
qtivtransform ! video/x-raw,format=BGRA,width=640,height=480 ! {QUEUE_LITE} ! mixer.'

OBJECT_DETECTION = f'<DATA_SRC> ! \
tee name=split \
split. ! {QUEUE_LITE} ! qtivcomposer name=mixer sink_1::dimensions="<640,480>" ! {QUEUE_LITE} ! <DISPLAY_SINK> \
split. ! {QUEUE_LITE} ! qtimlvconverter ! {QUEUE_LITE} ! qtimltflite delegate=external external-delegate-path=libQnnTFLiteDelegate.so \
external-delegate-options="QNNExternalDelegate,backend_type=htp;" model=/etc/models/yolox_quantized.tflite ! {QUEUE_LITE} ! \
qtimlpostprocess settings="{{\\"confidence\\": 75.0}}" results=10 module=yolov8 labels=/etc/labels/yolox.json ! \
qtivtransform ! video/x-raw,format=BGRA,width=640,height=360 ! {QUEUE_LITE} ! mixer.'

DEPTH_SEGMENTATION = f'<DATA_SRC> ! tee name=split \
split. ! {QUEUE_LITE} ! qtivcomposer background=0 name=dual \
sink_0::position=<0,0> sink_0::dimensions=<640,480> \
sink_1::position=<0,480> sink_1::dimensions=<640,480> ! {QUEUE_LITE} ! <DISPLAY_SINK> \
split. ! {QUEUE_LITE} ! qtimlvconverter ! {QUEUE_LITE} ! qtimltflite delegate=external external-delegate-path=libQnnTFLiteDelegate.so \
external-delegate-options=QNNExternalDelegate,backend_type=htp model=/etc/models/midas_quantized.tflite ! {QUEUE_LITE} ! \
qtimlpostprocess module=midas-v2 labels=/etc/labels/monodepth.json ! \
qtivtransform ! video/x-raw,width=640,height=480 ! {QUEUE_LITE} ! dual.sink_1'

SEGMENTATION = f'<DATA_SRC> ! tee name=split \
split. ! {QUEUE_LITE} ! qtivcomposer name=mixer sink_1::alpha=0.5 ! {QUEUE_LITE} ! <DISPLAY_SINK> \
split. ! {QUEUE_LITE} ! qtimlvconverter ! {QUEUE_LITE} ! qtimltflite delegate=external external-delegate-path=libQnnTFLiteDelegate.so \
external-delegate-options="QNNExternalDelegate,backend_type=htp;" model=/etc/models/deeplabv3_plus_mobilenet_quantized.tflite ! {QUEUE_LITE} ! \
qtimlpostprocess module=deeplab-argmax labels=/etc/labels/deeplabv3_resnet50.json ! \
qtivtransform ! video/x-raw,width=256,height=144 ! {QUEUE_LITE} ! mixer.'

APP_NAME = f"QCS6490 Vision AI"

TRIA = r"""
████████╗██████╗ ██╗ █████╗ 
╚══██╔══╝██╔══██╗██║██╔══██╗
   ██║   ██████╔╝██║███████║
   ██║   ██╔══██╗██║██╔══██║
   ██║   ██║  ██║██║██║  ██║
   ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝
"""


def lerp(a, b, t):
    """Linear interpolation between two values"""
    return a + t * (b - a)


def inverse_lerp(a, b, v):
    """Inverse linear interpolation between two values"""
    return (v - a) / (b - a) if a != b else 0.0


def get_ema(x_cur, x_last, alpha=0.75):
    """
    Exponential moving average

    Args:
        x_cur: Current value
        x_last: Last value
        alpha: Smoothing factor

    Note:
        alpha is a misnomer. alpha = 1.0 is equivalent to no smoothing

    Ref:
        https://en.wikipedia.org/wiki/Exponential_smoothing

    """
    return alpha * x_cur + (1 - alpha) * x_last


def app_version():
    """Get the latest tag or commit hash if possible, unknown otherwise"""

    try:
        version = subprocess.check_output(
            ["git", "describe", "--tags", "--always"], text=True
        ).strip()
        date = subprocess.check_output(
            ["git", "log", "-1", "--format=%cd", "--date=short"], text=True
        ).strip()

        return f"{version} {date}"
    except subprocess.CalledProcessError:
        # Handle errors, such as not being in a Git repository
        return "unknown"


APP_HEADER = f"{APP_NAME} v({app_version()})"

#gst-launch-1.0 -e --gst-debug=2 v4l2src device=/dev/v4l/by-id/usb-046d_Logi_Webcam_C920e_FF7FCEDF-video-index0 name=videosource ! qtivtransform ! video/x-raw,format=RGB,width=640,height=480,framerate=30/1 ! identity signal-handoffs=true name=id ! tee name=split split. ! queue max-size-buffers=1 leaky=downstream ! qtivcomposer name=mixer ! fpsdisplaysink text-overlay=true video-sink=gtksink name="videosink" sync=false split. ! queue max-size-buffers=1 leaky=downstream ! qtimlvconverter ! queue max-size-buffers=1 leaky=downstream ! qtimltflite delegate=external external-delegate-path=libQnnTFLiteDelegate.so external-delegate-options="QNNExternalDelegate,backend_type=htp;" model=/etc/models/hrnet_pose_quantized.tflite ! queue max-size-buffers=1 leaky=downstream ! qtimlpostprocess results=2 module=hrnet labels=/etc/labels/hrnet_pose.json settings=/etc/labels/hrnet_settings.json ! qtivtransform ! video/x-raw,format=BGRA,width=640,height=360 ! queue max-size-buffers=1 leaky=downstream ! mixer.