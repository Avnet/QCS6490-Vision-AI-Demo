#!/bin/bash

BASE_DIR=""
DEMO_APP_DIR=$BASE_DIR"/opt/QCS6490-Vision-AI-Demo"
outputmodelpath="/etc/models"
outputlabelpath="/etc/labels"

echo "Make file system writable"
mount -o remount,rw /

##### Make demo executable  #####
chmod -R +x $DEMO_APP_DIR

##### Download ML artifacts #####

# Helper functions
# Function to download files
download_file() {

    local url="$1"
    local target_path="$2"
    local filename
    filename=$(basename "$target_path")

    echo "📥 Downloading $url..."

    # Download the file using curl with error handling
    if ! curl -fL -o "$filename" "$url"; then
        echo "❌ Error: Failed to download $url"
        exit 1
    fi

    # Create the target directory if it doesn't exist
    local target_dir
    target_dir=$(dirname "$target_path")
    if [ ! -d "$target_dir" ]; then
        echo "📁 Target directory '$target_dir' does not exist. Creating it..."
        mkdir -p "$target_dir"
    fi

    # Move the file to the target path
    if ! mv "$filename" "$target_path"; then
        echo "❌ Error: Failed to move $filename to $target_path"
        exit 1
    fi

    echo "✅ File downloaded and moved to $target_path"
	echo ""
}

mkdir -p "${outputmodelpath}"
mkdir -p "${outputlabelpath}"

### Labels
download_file "https://raw.githubusercontent.com/quic/sample-apps-for-qualcomm-linux/refs/heads/main/artifacts/json_labels/hrnet_pose.json" "${outputlabelpath}/hrnet_pose.json"
download_file "https://raw.githubusercontent.com/quic/sample-apps-for-qualcomm-linux/refs/heads/main/artifacts/json_labels/classification.json" "${outputlabelpath}/classification.json"
download_file "https://raw.githubusercontent.com/quic/sample-apps-for-qualcomm-linux/refs/heads/main/artifacts/json_labels/deeplabv3_resnet50.json" "${outputlabelpath}/deeplabv3_resnet50.json"
download_file "https://raw.githubusercontent.com/quic/sample-apps-for-qualcomm-linux/refs/heads/main/artifacts/json_labels/yolox.json" "${outputlabelpath}/yolox.json"
download_file "https://raw.githubusercontent.com/quic/sample-apps-for-qualcomm-linux/refs/heads/main/artifacts/json_labels/monodepth.json" "${outputlabelpath}/monodepth.json"


### Model files
download_file "https://huggingface.co/qualcomm/Inception-v3/resolve/60c6a08f58919a0dc7e005ec02bdc058abb1181b/Inception-v3_w8a8.tflite" "${outputmodelpath}/inception_v3_quantized.tflite"
download_file "https://huggingface.co/qualcomm/DeepLabV3-Plus-MobileNet/resolve/fa276f89cce8ed000143d40e8887decbbea57012/DeepLabV3-Plus-MobileNet_w8a8.tflite" "${outputmodelpath}/deeplabv3_plus_mobilenet_quantized.tflite"
download_file "https://huggingface.co/qualcomm/HRNetPose/resolve/dbfe1866bd2dbfb9eecb32e54b8fcdc23d77098b/HRNetPose_w8a8.tflite" "${outputmodelpath}/hrnet_pose_quantized.tflite"
download_file "https://huggingface.co/qualcomm/Midas-V2/resolve/13de42934d09fe7cda62d7841a218cbb323e7f7e/Midas-V2_w8a8.tflite" "${outputmodelpath}/midas_quantized.tflite"
download_file "https://huggingface.co/qualcomm/Yolo-X/resolve/2885648dda847885e6fd936324856b519d239ee1/Yolo-X_w8a8.tflite" "${outputmodelpath}/yolox_quantized.tflite"


### Settings
download_file "https://raw.githubusercontent.com/quic/sample-apps-for-qualcomm-linux/refs/heads/main/artifacts/json_labels/hrnet_settings.json" "${outputlabelpath}/hrnet_settings.json"
