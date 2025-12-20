# ContexGo: Personal Context Intelligence Agent

> **Quantify Locally. Think Globally.**
>
> 一个“本地感知 + 云端思考”的个人上下文智能体。它在本地提取行为语义，通过双重安全网关脱敏后，利用云端大模型构建可被解释、修正和重算的“第二大脑”。

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

---

## 📖 项目背景 (Introduction)

**ContexGo** 致力于解决个人数字助理领域的一个核心矛盾：**本地算力的局限性与认知洞察的高质量需求之间的断裂。**

传统的本地大模型方案往往拖累系统性能，而纯云端方案又面临严重的隐私风险。ContexGo 采用 **“瘦客户端 (Thin Client)”** 架构：
1.  **本地 (Local):** 负责极低功耗的数据采集、清洗与**本地词元提取 (Token Extraction)**。
2.  **云端 (Cloud):** 负责高维度的语义推理与心理状态分析（接入 DeepSeek-V3 / GPT-4o）。

---

## 🏗️ 核心架构 (Architecture Principles)

### 1. 混合计算模型 (Hybrid Compute Model)
* **Hard Core (Local):** 复刻 [MineContext](https://github.com/volcengine/MineContext) 的逻辑。使用系统级 API（Accessibility/Windows OCR）直接提取屏幕文本，**不上传任何截图到云端**。
* **Soft Brain (Cloud):** 接收 JSON 纯文本摘要，返回高质量的心理侧写与行为建议。

### 2. 双重拒绝器 (Dual Gatekeepers)
为了适配云端架构，系统引入了两层拦截机制：
* **Pre-flight Gatekeeper (发送前):** **隐私与成本控制。** 拦截敏感词（如密码、身份证号），合并碎片请求，并在上下文无变化（低熵）时阻止 API 调用以节省费用。
* **Post-flight Gatekeeper (接收后):** **质量与安全控制。** 过滤云端返回的幻觉内容、重复建议或格式错误的指令。

### 3. 懒惰采样 (Lazy Sampling)
采用 **“事件驱动 + 长间隔兜底”** 策略（>10s），仅在窗口切换或长时间活跃时捕捉快照，确保后台运行几乎零负载。

---

## 🧩 模块详解 (Modules)

### 🛡️ Module I: Sentinel (本地感知)
*轻量化，无 GPU 依赖*
* **Smart Monitor:** 监听窗口句柄与键鼠活跃度。
* **Local Tokenizer:**
    * **Accessibility API:** 直接读取 UI 树获取文本（VSCode 文件名, 浏览器 URL），零算力消耗。
    * **Windows OCR:** 仅在必要时调用本地离线 OCR 引擎提取图像文本。
    * **Privacy Lock:** **原始截图在提取文本后立即内存销毁，绝不落盘，绝不上传。**

### ⚙️ Module II: Processing (结构化)
* **Time Aggregator:** 将离散的采样点聚合为 5 分钟粒度的 **TimeWindow** 对象。
* **Context Clustering:** 在本地进行初步的规则聚类（如识别 Project A vs Project B），减少发往云端的 Token 数量。

### ☁️ Module III: Brain (云端大脑)
* **Cloud Client:** 兼容 OpenAI 接口标准的客户端（支持 DeepSeek, Moonshot, ChatGPT）。
* **Analyst:** 周期性（如每 15 分钟）发送压缩后的 JSON 摘要，请求云端进行深度心理推理。
* **Cost Control:** 动态调整采样发送频率，避免由静止画面产生无效 API 开销。

### 🖥️ Module IV: Interaction (Flet UI)
* **Dashboard:** 可视化展示时间轴与云端生成的 Insight。
* **Intervention:** Windows 系统级弹窗。仅在 Gatekeeper 放行高置信度建议时触发。

---

## 🛠️ 技术栈 (Tech Stack)

| 模块 | 技术选型 | 说明 |
| :--- | :--- | :--- |
| **GUI Framework** | **Flet** | Python wrapper for Flutter，单进程高性能渲染 |
| **Cloud LLM** | **OpenAI SDK** | 接入 **DeepSeek-V3** (推荐) 或 GPT-4o |
| **Local OCR** | **Windows.Media.Ocr** | 离线、免费、系统级文本提取 |
| **Capture** | **MSS / Win32 API** | 毫秒级截图与句柄获取 |
| **Storage** | **SQLite** | 本地结构化事件存储 |

---

## ⚠️ 隐私与安全声明

1.  **数据最小化:** 云端大模型**仅能看到**经过脱敏的纯文本 JSON 摘要（如 `{"app": "VSCode", "title": "main.py"}`）。
2.  **截图本地化:** 所有的视觉数据处理（截图、OCR）均在本地内存中完成，**严禁**将图像二进制数据发送至网络。
3.  **主动脱敏:** Pre-flight Gatekeeper 会在上传前通过正则强制过滤常见的 PII（个人身份信息）。

## 🤝 贡献 (Contributing)

欢迎提交 Issue 和 Pull Request。

## 📄 License

**GNU Affero General Public License v3.0 (AGPLv3)**


