# ContexGo: Personal Context Intelligence Agent

> **Quantify Locally. Think Globally. Sync Seamlessly.**
>
> 一个“本地感知 + 云端思考”的个人上下文智能体。它在本地提取行为语义，利用云端大模型构建“第二大脑”，并通过 CRDT + Tailscale 实现多设备间的无缝记忆同步。

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

---

## 📖 项目背景 (Introduction)

**ContexGo** 致力于解决个人数字助理领域的一个核心矛盾：**本地算力的局限性与认知洞察的高质量需求之间的断裂。**

传统的本地大模型方案往往拖累系统性能，而纯云端方案又面临严重的隐私风险。ContexGo 采用 **“瘦客户端 (Thin Client)”** 架构：
1.  **本地 (Local):** 负责极低功耗的数据采集、清洗与**本地词元提取 (Token Extraction)**。
2.  **云端 (Cloud):** 负责高维度的语义推理与心理状态分析（接入 DeepSeek-V3 / GPT-4o）。
3.  **多端 (Sync):** 基于 CRDT 技术与虚拟局域网，将你在台式机、笔记本等不同设备上的行为碎片，自动编织成一张完整的全天候上下文网络。

---

## 🏗️ 核心架构 (Architecture Principles)

### 1. 混合计算模型 (Hybrid Compute Model)
* **Hard Core (Local):** 复刻 [MineContext](https://github.com/volcengine/MineContext) 的逻辑。使用系统级 API（Accessibility/Windows OCR）直接提取屏幕文本，**不上传任何截图到云端**。
* **Soft Brain (Cloud):** 接收 JSON 纯文本摘要，返回高质量的心理侧写与行为建议。

### 2. 实用的去中心化同步 (Pragmatic Decentralized Sync)
* **Data Layer (CRDT):** 采用 **CRDT (Conflict-free Replicated Data Type)** 数据结构。无论网络如何抖动，多设备间的状态合并永远不会产生冲突。
* **Network Layer (Overlay):** 摒弃复杂的公网 IP 和 NAT 穿透开发，推荐使用 **Tailscale / ZeroTier** 构建虚拟局域网。ContexGo 监听虚拟 IP，从而在任何网络环境下（如家 vs 咖啡馆）实现安全的 P2P 直连。

### 3. 双重拒绝器 (Dual Gatekeepers)
为了适配云端架构，系统引入了两层拦截机制：
* **Pre-flight Gatekeeper (发送前):** **隐私与成本控制。** 拦截敏感词（如密码、身份证号），合并碎片请求，并在上下文无变化（低熵）时阻止 API 调用以节省费用。
* **Post-flight Gatekeeper (接收后):** **质量与安全控制。** 过滤云端返回的幻觉内容、重复建议或格式错误的指令。

### 4. 懒惰采样 (Lazy Sampling)
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

### 🔄 Module III: Synchronization (多端同步)
* **Network Transport:** 依赖 **Tailscale** 提供的虚拟局域网环境，实现开箱即用的 P2P 通信。
* **CRDT Engine:** 使用 `y-py` (Yjs) 管理分布式状态。
* **Timeline Merging:** 智能合并多设备状态。
    * *场景:* 此时 PC (Ryzen) 处于 Idle，Laptop 处于 Coding -> 合并结果为 Coding。

### ☁️ Module IV: Brain (云端大脑)
* **Cloud Client:** 兼容 OpenAI 接口标准的客户端（支持 DeepSeek, Moonshot, ChatGPT）。
* **Analyst:** 周期性（如每 15 分钟）发送压缩后的 JSON 摘要（**包含所有已同步设备的合并上下文**），请求云端进行深度心理推理。

### 🖥️ Module V: Interaction (Flet UI)
* **Dashboard:** 可视化展示多端合并后的时间轴与云端生成的 Insight。
* **Intervention:** Windows 系统级弹窗。仅在 Gatekeeper 放行高置信度建议时触发。

---

## 🛠️ 技术栈 (Tech Stack)

| 模块 | 技术选型 | 说明 |
| :--- | :--- | :--- |
| **GUI Framework** | **Flet** | Python wrapper for Flutter，单进程高性能渲染 |
| **Sync Engine** | **y-py (Yjs)** | 高性能 CRDT 库，处理数据合并 |
| **Connectivity** | **Tailscale** | (推荐) 虚拟组网工具，解决 NAT/公网连接问题 |
| **Cloud LLM** | **OpenAI SDK** | 接入 **DeepSeek-V3** (推荐) 或 GPT-4o |
| **Local OCR** | **Windows.Media.Ocr** | 离线、免费、系统级文本提取 |
| **Storage** | **SQLite** | 本地结构化事件存储 |

---


## ⚠️ 隐私与安全声明

1.  **数据最小化:** 云端大模型**仅能看到**经过脱敏的纯文本 JSON 摘要。
2.  **截图本地化:** 所有的视觉数据处理均在本地内存中完成，**严禁**上传图像。
3.  **同步安全:** Tailscale 提供基于 WireGuard 的端到端加密传输，确保设备间通信无法被窃听。

## 🤝 贡献 (Contributing)

欢迎提交 Issue 和 Pull Request。

## 📄 License

**GNU Affero General Public License v3.0 (AGPLv3)**
