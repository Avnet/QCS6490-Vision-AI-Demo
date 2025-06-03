"""Common utilities and constants for VAI demo"""

import subprocess

GRAPH_SAMPLE_WINDOW_SIZE_s = 31
HW_SAMPLING_PERIOD_ms = 250
GRAPH_DRAW_PERIOD_ms = 30
AUTOMATIC_DEMO_SWITCH_s = 60

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

# WARN: These commands will be processed by application. Tags like <TAG> are likely placeholder

# Having one default is fine, as we can extrapolate for the other window
DEFAULT_LEFT_WINDOW = "gtksink name=sink1"
DEFAULT_DUAL_WINDOW = "gtksink name=sink2"

# TODO: add FPS support for camera?
# TODO: What is the most reasonable caps res out of camera? Seems to be 640x480 when running two usb 2.0 cams
CAMERA = f"<DATA_SRC> ! qtivtransform ! video/x-raw,format=BGRA,width=640,height=480,framerate=30/1 ! {DEFAULT_LEFT_WINDOW}"

POSE_DETECTION = "<DATA_SRC> ! qtivtransform ! video/x-raw,format=NV12_Q08C,width=640,height=480,framerate=30/1 ! \
tee name=split \
split. ! queue ! qtivcomposer name=mixer ! <SINGLE_DISPLAY> \
split. ! queue ! qtimlvconverter ! qtimltflite delegate=external external-delegate-path=libQnnTFLiteDelegate.so external-delegate-options=\"QNNExternalDelegate,backend_type=htp;\" \
model=/opt/posenet_mobilenet_v1.tflite ! qtimlvpose threshold=51.0 results=2 module=posenet labels=/opt/posenet_mobilenet_v1.labels \
constants=\"Posenet,q-offsets=<128.0,128.0,117.0>,q-scales=<0.0784313753247261,0.0784313753247261,1.3875764608383179>;\" ! video/x-raw,format=BGRA,width=640,height=480 ! mixer."

CLASSIFICATION = '<DATA_SRC> ! qtivtransform ! video/x-raw,format=NV12_Q08C,width=640,height=480,framerate=30/1 ! \
tee name=split \
split. ! queue ! qtivcomposer name=mixer sink_1::position="<30,30>" sink_1::dimensions="<320, 180>" ! queue ! <SINGLE_DISPLAY> \
split. ! queue ! qtimlvconverter ! queue ! qtimlsnpe delegate=dsp model=/opt/inceptionv3.dlc ! queue ! qtimlvclassification threshold=40.0 results=2 \
module=mobilenet labels=/opt/classification.labels ! video/x-raw,format=BGRA,width=640,height=360 ! queue ! mixer.'

OBJECT_DETECTION = '<DATA_SRC> ! qtivtransform ! video/x-raw,format=NV12_Q08C,width=640,height=480,framerate=30/1 ! \
tee name=split \
split. ! queue ! qtivcomposer name=mixer1 ! queue ! <SINGLE_DISPLAY> \
split. ! queue ! qtimlvconverter ! queue ! qtimlsnpe delegate=dsp model=/opt/yolonas.dlc layers="</heads/Mul, /heads/Sigmoid>" ! queue ! qtimlvdetection threshold=51.0 results=10 module=yolo-nas labels=/opt/yolonas.labels \
! video/x-raw,format=BGRA,width=640,height=480 ! queue ! mixer1.'

DEPTH_SEGMENTATION = "<DATA_SRC> ! qtivtransform ! \
    video/x-raw,format=NV12_Q08C,width=640,height=480,framerate=30/1 ! \
    tee name=split \
    split. ! queue ! qtivcomposer background=0 name=dual \
        sink_0::position=\<0,0\> sink_0::dimensions=\<960,720\> \
        sink_1::position=\<960,0\> sink_1::dimensions=\<960,720\> \
    ! queue ! <DUAL_DISPLAY> \
    split. ! queue ! qtimlvconverter ! queue ! \
        qtimltflite delegate=external \
            external-delegate-path=libQnnTFLiteDelegate.so \
            external-delegate-options=QNNExternalDelegate,backend_type=htp \
            model=/opt/Midas-V2-Quantized.tflite ! queue ! \
        qtimlvsegmentation module=midas-v2 labels=/opt/monodepth.labels \
            constants=\"Midas,q-offsets=<0.0>,q-scales=<4.716535568237305>;\" ! \
        video/x-raw,width=960,height=720 ! queue ! dual.sink_1"

SEGMENTATION = '<DATA_SRC> ! qtivtransform ! video/x-raw,format=NV12_Q08C,width=640,height=480,framerate=30/1 !queue ! tee name=split \
split. ! queue ! qtivcomposer name=mixer sink_1::alpha=0.65 ! queue ! <SINGLE_DISPLAY> \
split. ! queue ! \
  qtimlvconverter ! queue ! \
  qtimltflite \
      delegate=external \
      external-delegate-path=libQnnTFLiteDelegate.so \
      external-delegate-options="QNNExternalDelegate,backend_type=htp" \
      model=/opt/deeplabv3_plus_mobilenet_quantized.tflite ! queue ! \
  qtimlvsegmentation \
      module=deeplab-argmax \
      labels=/opt/voc_labels.txt \
      constants="deeplab,q-offsets=<0.0>,q-scales=<1.0>" ! \
  video/x-raw,format=BGRA,width=640,height=480 ! \
  queue ! mixer.'


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
