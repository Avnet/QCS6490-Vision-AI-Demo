"""Common utilities and constants for VAI demo"""

import subprocess

GRAPH_SAMPLE_WINDOW_SIZE_s = 31
HW_SAMPLING_PERIOD_ms = 250
GRAPH_DRAW_PERIOD_ms = 30
AUTOMATIC_DEMO_SWITCH_s = 120
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

QUEUE_LITE = 'queue max-size-buffers=1 leaky=downstream flush-on-eos=1 '

USB_CAM_CAPS  = ' ! qtivtransform ! video/x-raw,format=NV12,width=640,height=480,framerate=30/1 '
# compression=ubwc labels the DMA-BUF as UBWC-compressed so the consumer-side
# capsfilter after qtisocketsrc can assert the same flag, telling hardware
# elements (qtimlvconverter, qtivtransform) to take the hardware path.
MIPI_CAM_CAPS = ' ! video/x-raw,format=NV12_Q08C,width=640,height=480,framerate=30/1,compression=ubwc '

# Unix domain socket paths for the qtisocketsink/qtisocketsrc DMA-BUF bridge.
CAM_SOCKET_0 = '/tmp/vai_cam0.sock'
CAM_SOCKET_1 = '/tmp/vai_cam1.sock'

QTIM_TFLITE = 'qtimltflite delegate=external external-delegate-path=libQnnTFLiteDelegate.so external-delegate-options="QNNExternalDelegate,backend_type=htp;"'

_Q = QUEUE_LITE

# Camera branch: NV12_Q08C UBWC → hardware BGRA conversion → CPU-accessible appsink.
# qtivtransform here produces scanout-linear BGRA that extract_dup() can mmap.
_CAM_SINK = (
    f'! {_Q}! qtivtransform ! video/x-raw,format=BGRA,width=640,height=480 '
    f'! {_Q}! appsink name=videosink emit-signals=true sync=false'
)

# ML overlay branch terminal: videoconvert output is always CPU-accessible.
_ML_SINK = f'! {_Q}! appsink name=mlsink emit-signals=true sync=false'

CAMERA = f'<DATA_SRC> {_CAM_SINK}'

POSE_DETECTION = (
    f'<DATA_SRC> ! tee name=split '
    f'split. {_CAM_SINK} '
    f'split. ! {_Q}! qtimlvconverter ! {_Q}! {QTIM_TFLITE} model=/etc/models/hrnet_pose_quantized.tflite '
    f'! {_Q}! qtimlpostprocess results=2 module=hrnet labels=/etc/labels/hrnet_pose.json settings=/etc/labels/hrnet_settings.json '
    f'! videoconvert ! video/x-raw,format=BGRA,width=640,height=360 {_ML_SINK}'
)

CLASSIFICATION = (
    f'<DATA_SRC> ! tee name=split '
    f'split. {_CAM_SINK} '
    f'split. ! {_Q}! qtimlvconverter ! {_Q}! {QTIM_TFLITE} model=/etc/models/inception_v3_quantized.tflite '
    f'! {_Q}! qtimlpostprocess settings="{{\\"confidence\\": 40.0}}" results=2 module=mobilenet-softmax labels=/etc/labels/classification.json '
    f'! videoconvert ! video/x-raw,format=BGRA,width=640,height=480 {_ML_SINK}'
)

OBJECT_DETECTION = (
    f'<DATA_SRC> ! tee name=split '
    f'split. {_CAM_SINK} '
    f'split. ! {_Q}! qtimlvconverter ! {_Q}! {QTIM_TFLITE} model=/etc/models/yolox_quantized.tflite '
    f'! {_Q}! qtimlpostprocess settings="{{\\"confidence\\": 75.0}}" results=10 module=yolov8 labels=/etc/labels/yolox.json '
    f'! videoconvert ! video/x-raw,format=BGRA,width=640,height=360 {_ML_SINK}'
)

DEPTH_SEGMENTATION = (
    f'<DATA_SRC> ! tee name=split '
    f'split. {_CAM_SINK} '
    f'split. ! {_Q}! qtimlvconverter ! {_Q}! {QTIM_TFLITE} model=/etc/models/midas_quantized.tflite '
    f'! {_Q}! qtimlpostprocess module=midas-v2 labels=/etc/labels/monodepth.json '
    f'! videoconvert ! video/x-raw,format=BGRA,width=640,height=480 {_ML_SINK}'
)

SEGMENTATION = (
    f'<DATA_SRC> ! tee name=split '
    f'split. {_CAM_SINK} '
    f'split. ! {_Q}! qtimlvconverter ! {_Q}! {QTIM_TFLITE} model=/etc/models/deeplabv3_plus_mobilenet_quantized.tflite '
    f'! {_Q}! qtimlpostprocess module=deeplab-argmax labels=/etc/labels/deeplabv3_resnet50.json '
    f'! videoconvert ! video/x-raw,format=BGRA,width=256,height=144 {_ML_SINK}'
)

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


APP_HEADER = f"{APP_NAME}"
