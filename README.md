  ![image](https://github.com/user-attachments/assets/7117af53-3e5a-4fbb-9638-94e3e513269e)
# 🔍 Multi-Stream Vision-AI Reference Design
**Powered by Qualcomm Hexagon AI Engine**  
**License: MIT**

**Branch features:**
**Support for 1080p displays - Support for QLI.1.5 - DSP utilization visualization**

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
