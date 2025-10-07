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


download_file "https://raw.githubusercontent.com/quic/sample-apps-for-qualcomm-linux/refs/heads/main/artifacts/labels/hrnet_pose.labels" "${outputlabelpath}/hrnet_pose.labels"
download_file "https://raw.githubusercontent.com/quic/sample-apps-for-qualcomm-linux/refs/heads/main/artifacts/labels/classification.labels" "${outputlabelpath}/classification.labels"
download_file "https://raw.githubusercontent.com/quic/sample-apps-for-qualcomm-linux/refs/heads/main/artifacts/labels/deeplabv3_resnet50.labels" "${outputlabelpath}/voc_segmentation.labels"
download_file "https://raw.githubusercontent.com/quic/sample-apps-for-qualcomm-linux/refs/heads/main/artifacts/labels/detection.labels" "${outputlabelpath}/yolox.labels"
download_file "https://qaihub-public-assets.s3.us-west-2.amazonaws.com/qai-hub-models/models/midas/midasv2_linux_assets/monodepth.labels" "${outputlabelpath}/monodepth.labels"

download_file "https://huggingface.co/qualcomm/Inception-v3/resolve/60c6a08f58919a0dc7e005ec02bdc058abb1181b/Inception-v3_w8a8.tflite" "${outputmodelpath}/inception_v3_quantized.tflite"
download_file "https://huggingface.co/qualcomm/FCN-ResNet50/resolve/3951b964f2b231d28ca0d04091dc661b0cc3f53c/FCN-ResNet50_w8a8.tflite" "${outputmodelpath}/fcn_resnet50_quantized.tflite"
download_file "https://huggingface.co/qualcomm/HRNetPose/resolve/dbfe1866bd2dbfb9eecb32e54b8fcdc23d77098b/HRNetPose_w8a8.tflite" "${outputmodelpath}/hrnet_pose_quantized.tflite"
download_file "https://huggingface.co/qualcomm/Midas-V2/resolve/13de42934d09fe7cda62d7841a218cbb323e7f7e/Midas-V2_w8a8.tflite" "${outputmodelpath}/midas_quantized.tflite"
download_file "https://huggingface.co/qualcomm/Yolo-X/resolve/2885648dda847885e6fd936324856b519d239ee1/Yolo-X_w8a8.tflite" "${outputmodelpath}/yolox_quantized.tflite"
