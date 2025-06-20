#!/bin/bash

#Sample installer command
#makeself ~/demos/QCS6490-Vision-AI-Demo-Installer-project QCS6490-Vision-AI-Demo-Installer.run "Installing TRIA QCOMM demos" ./install.sh

#change BASE_DIR for testing
#BASE_DIR="/home/user/demos/extracted"
BASE_DIR=""
WESTON_DIR=$BASE_DIR"/etc/xdg/weston"
IMAGES_DIR=$BASE_DIR"/opt"
LAUNCH_DIR=$BASE_DIR"/opt"
DEMO_DIR=$BASE_DIR"/opt"
AI_DIR=$BASE_DIR"/opt"
DEMO_APP_DIR=$DEMO_DIR"/QCS6490-Vision-AI-Demo"

echo "Make file system writable"
mount -o remount,rw /

# Create weston folder if not oresent
mkdir -p $WESTON_DIR

if [ $? -ne 0 ]
then
    echo "Make file system writable - failed"
fi

setenforce 0

echo "Update weston.ini"
yes | cp -rf weston.ini $WESTON_DIR
if [ $? -ne 0 ]
then
    echo "Update weston.ini - failed"
fi

echo "Update images"
yes | cp -rf resources/*.png $IMAGES_DIR
if [ $? -ne 0 ]
then
    echo "Update images - failed"
fi

echo "Update launchers"
yes | cp -rf resources/GSTLauncher.glade $LAUNCH_DIR
if [ $? -ne 0 ]
then
    echo "Update launchers - failed"
fi
chmod +x $LAUNCH_DIR/*.sh

chmod -R +x $DEMO_APP_DIR

echo "Make file system writable"
mount -o rw,remount /usr/

echo "Update icons"
yes | cp -rf files/icons/* $ICONS_DIR



echo "Update PSUTIL"
# Setup filesystem to remove outdated psutil. This assumes a stock image only comes with one psutil verison installed,
# But I think a fresh BSP might actually have two psutil packages... Calling uninstall might not get both
mount -o remount,rw /usr
pip3 install psutil==7.0.0

##### Download artifacts #####

# Helper functions
# Function to download files
download_file() {
    local url=$1
    local output_dir=$2
    curl -L -O "$url"
    mv "$(basename "$url")" "$output_dir"
    #Cross Check again: cp "$(basename "$url")" "$output_dir"
}

outputmodelpath="/etc/models"
outputlabelpath="/etc/labels"

mkdir -p "${outputmodelpath}"
mkdir -p "${outputlabelpath}"


download_file "https://raw.githubusercontent.com/quic/sample-apps-for-qualcomm-linux/refs/heads/main/artifacts/labels/hrnet_pose.labels" "${outputlabelpath}"
download_file "https://raw.githubusercontent.com/quic/sample-apps-for-qualcomm-linux/refs/heads/main/artifacts/labels/classification.labels" "${outputlabelpath}"
download_file "https://raw.githubusercontent.com/quic/sample-apps-for-qualcomm-linux/refs/heads/main/artifacts/labels/deeplabv3_resnet50.labels" "${outputlabelpath}"
download_file "https://raw.githubusercontent.com/quic/sample-apps-for-qualcomm-linux/refs/heads/main/artifacts/labels/detection.labels" "${outputlabelpath}/yolox.labels"
download_file "https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-models/models/midas/midasv2_linux_assets/monodepth.labels" "${outputlabelpath}/"

download_file "https://huggingface.co/qualcomm/Inception-v3-Quantized/resolve/b98244bed30190a9cf02346fe75279bde74da11e/Inception-v3-Quantized.tflite" "${outputmodelpath}/inception_v3_quantized.tflite"
download_file "https://huggingface.co/qualcomm/DeepLabV3-Plus-MobileNet-Quantized/resolve/e66a9a8d095a39543ea3495e73573da7cda36450/DeepLabV3-Plus-MobileNet-Quantized.tflite" "${outputmodelpath}/deeplabv3_plus_mobilenet_quantized.tflite"
download_file "https://huggingface.co/qualcomm/HRNetPoseQuantized/resolve/d46ec7f8bfe324b2087b19f08db1962ef5abf2be/HRNetPoseQuantized.tflite" "${outputmodelpath}/hrnet_pose_quantized.tflite"
download_file "https://huggingface.co/qualcomm/Midas-V2-Quantized/resolve/8618a9de03527a4993674b72254ae999d1116fbc/Midas-V2-Quantized.tflite" "${outputmodelpath}/midas_quantized.tflite"
download_file "https://huggingface.co/qualcomm/Yolo-X/resolve/2885648dda847885e6fd936324856b519d239ee1/Yolo-X_w8a8.tflite" "${outputmodelpath}/yolox_quantized.tflite"