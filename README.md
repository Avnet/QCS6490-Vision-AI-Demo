  ![image](https://github.com/user-attachments/assets/7117af53-3e5a-4fbb-9638-94e3e513269e)
# 🔍 Multi-Stream Vision-AI Reference Design
**Powered by Qualcomm Hexagon AI Engine**  
**License: MIT**

![vai_sample1_wave_edited](https://github.com/user-attachments/assets/8f4f451c-39e9-40a5-98fb-a428ed6d7152)

## Overview

This reference design demonstrates a **multi-camera, multi-model AI pipeline** using the **Tria VisionAI-Kit 6490**. Built with **Python, GTK, and GStreamer**, this GUI-based application allows users to:

- 🔄 Run **up to two AI models concurrently** on separate camera inputs  
- 🎥 Stream live camera feeds with overlays from selected AI models  
- 📊 Visualize **real-time system performance and thermal metrics**  
- 🚀 Leverage Qualcomm’s **Hexagon DSP AI Engine** for efficient, low-power inference  

Currently supported ML pipelines include:
- Pose Detection  
- Depth Segmentation  
- Object Detection  
- Image Classification

With potential for more!

---

## 📈 System Monitoring

The design integrates two utilities for performance monitoring:
- **QProf** (Qualcomm's common Linux profiler)  
- **psutil** (a cross-platform system utility)  

### Live Metrics:
- CPU / Memory / GPU utilization  
- LPDDR5, CPU, and GPU temperature graphs  
- Track last N seconds (N=30 by default)

## How it works / Design Overview

![System Overview](https://github.com/user-attachments/assets/c1c6d54a-7cb9-438e-8bd9-0e5b8588bf13)

### Persistent Camera Processes & Socket Bridging

Each camera runs in its own long-lived subprocess, kept alive across ML model
switches so the QMMF/ISP camera session is never torn down between demos.
Frames are bridged into the active ML pipeline subprocess using GStreamer's
`qtisocketsink` / `qtisocketsrc` plugins:

- The persistent camera process (`qtiqmmfsrc` for MIPI, `v4l2src` for USB)
  pushes frames to a `qtisocketsink` over a Unix domain socket
  (e.g. `/tmp/vai_cam0.sock`), forwarded as DMA-BUF file descriptors.
- The selected ML pipeline attaches via `qtisocketsrc` on the same socket,
  with a capsfilter describing the exact buffer format being sent —
  `NV12_Q08C` with `compression=ubwc` for MIPI cameras, or plain `NV12` for
  USB cameras.
- Matching the caps after `qtisocketsrc` lets hardware elements
  (`qtimlvconverter`, `qtivtransform`) recognize UBWC-compressed DMA-BUF
  memory and take the hardware-accelerated path instead of falling back to a
  software copy.

This design allows the AI model running on a camera to be switched on the
fly without restarting the camera capture session.

---

## 🧰 Equipment List (As seen at Embedded World 2025)

Here’s the demo setup we showcased at Embedded World 2025:

![Equipment List](https://github.com/user-attachments/assets/34cb25cc-2648-46ce-92db-623024d78d81)

---

## 🔌 Hardware Notes

The **VisionAI-Kit 6490** is a platform designed for edge-AI (multi) camera applications. Key features include:

- Qualcomm QCS6490 SoC  
- Up to 4 MIPI camera inputs  
- Integrated Hexagon AI Engine  
- 8 GB LPDDR5 memory 

> ⚠️ *Note: although unlikely, HW could still be subject to change*

![Hardware Diagram](https://github.com/user-attachments/assets/8eca6561-6d67-4b09-b142-41cce7c09ac5)

---

## 🚧 Development Status

This project is actively maintained. Contributions, feedback, and issue reports are welcome!

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

![vai_sample1_wave_edited](https://github.com/user-attachments/assets/8f4f451c-39e9-40a5-98fb-a428ed6d7152)
