# ContexGo: Context-Aware Task State Agent

> **Capture. Structure. Align.**
>
> 一个本地优先的分布式上下文智能体。旨在通过工程化手段，将非结构化的行为流转换为可组合、可演算的任务状态，协助用户通过时间碎片的有序堆叠，实现从微观行为到宏观目标的对齐。

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Status: Architectural Design](https://img.shields.io/badge/Status-Blueprint_Phase-blue)]()

---

## 1. 初步设计图景 (Preliminary Vision)

本项目致力于构建一个**可持续的个人时间组合系统**。它不满足于仅仅记录“时间开销”，而是试图构建一个**“数字第二大脑”的索引层**。

系统设计遵循以下核心原则：
* **从简入繁 (Progressive Complexity):** 将底层的离散输入（IO信号/屏幕信息）抽象为原子化的“状态”，进而聚合为“会话”，最终映射至长期的“目标”。
* **管理即索引 (Management as Index):** “任务分类”是物理容器，“心理分析”是注入其中的语义灵魂。
* **分布式一致性 (Distributed Consistency):** 利用 CRDT 与虚拟组网，在多设备环境下维护统一的工作流视图，消除物理隔阂。

---

## 2. 核心抽象 (Core Abstractions)

系统不直接管理时间，而是管理**状态 (State)**。系统设计遵循以下三层抽象模型：

### L0: 信号层 (Signal Layer)
* **定义:** 物理世界与数字交互界面的原始投影。
* **特征:** 高频、离散、无语义、易变。
* **组成:** 窗口句柄变化、输入设备活跃度 (HID Activity)、屏幕内容的特征向量 (Feature Vectors)。

### L1: 状态层 (State Layer)
* **定义:** 基于信号特征分类得出的原子化时间切片。
* **特征:** 结构化、可枚举、具备基础属性（分类、投入度）。
* **逻辑:** 通过本地规则引擎或轻量级分类算法，将 L0 信号映射为特定的 `TaskState` (e.g., `Coding`, `Meeting`, `Idle`)。这是系统进行同步和基础统计的最小单元。

### L2: 认知层 (Cognitive Layer)
* **定义:** 对连续状态流的语义解释与目标偏差分析。
* **特征:** 语境化、长周期、具备心理侧写属性。
* **逻辑:** 利用大模型 (LLM) 分析 L1 状态序列，识别行为模式（如“心流”、“焦虑切换”），并评估其对预设目标的贡献度。

---

## 3. 系统架构详解 (System Architecture)

系统采用 **"本地计算核心 + 云端认知增强 + 虚拟组网同步"** 的混合架构。

### 🛡️ Module I: Sentinel (本地感知)
*轻量化，无 GPU 依赖*
* **Smart Monitor:** 监听窗口句柄与键鼠活跃度，采用“事件驱动”策略避免无效轮询。
* **Local Tokenizer:**
    * **Accessibility API:** 直接读取 UI 树获取文本（VSCode 文件名, 浏览器 URL），零算力消耗。
    * **Windows OCR:** 仅在必要时调用本地离线 OCR 引擎提取图像文本。
    * **Privacy Lock:** 原始截图在提取文本后立即内存销毁，绝不落盘，绝不上传。

### ⚙️ Module II: Processing (结构化)
* **Time Aggregator:** 将离散的采样点聚合为 5 分钟粒度的 **TimeWindow** 对象。
* **Context Clustering:** 在本地进行初步的规则聚类（复刻 MineContext 算法，如识别 Project A vs Project B），减少发往云端的 Token 数量。

### 🔄 Module III: Synchronization (多端同步)
* **Network Transport:** 依赖 **Tailscale** 提供的虚拟局域网环境，实现开箱即用的 P2P 通信，无需处理公网 NAT。
* **CRDT Engine:** 使用 **y-py** (Yjs) 管理分布式状态，确保数据最终一致性。
* **Timeline Merging:** 智能合并多设备状态。
    * *场景:* 此时 PC (Ryzen) 处于 Idle，Laptop 处于 Coding -> 合并结果为 Coding（最大投入度优先）。

### ☁️ Module IV: Brain (云端大脑)
* **Cloud Client:** 兼容 OpenAI 接口标准的客户端（支持 DeepSeek, Moonshot, ChatGPT）。
* **Analyst:** 周期性（如每 15 分钟）发送压缩后的 JSON 摘要（包含所有已同步设备的合并上下文），请求云端进行深度心理推理。
* **Gatekeeper:** 双重熔断机制（Pre-flight 脱敏/拦截，Post-flight 幻觉过滤）。

### 🖥️ Module V: Interaction (Flet UI)
* **Dashboard:** 可视化展示多端合并后的时间轴与云端生成的 Insight。
* **Intervention:** Windows 系统级弹窗。仅在 Gatekeeper 放行高置信度建议时触发。

---

## 4. 初步技术选型 (Preliminary Tech Stack)

| 模块 | 关键技术 | 选型理由 |
| :--- | :--- | :--- |
| **Language** | **Python 3.10+** | 胶水语言，生态丰富，完美适配 AI 与 UI 开发。 |
| **GUI Framework** | **Flet** | Python wrapper for Flutter，开发效率高，性能足够，支持原生窗口特性。 |
| **Sync Engine** | **y-py** | 基于 Rust 的高性能 CRDT 库，工业级分布式一致性解决方案。 |
| **Networking** | **Tailscale** | 虚拟组网工具，零配置实现 NAT 穿透与 P2P 加密通信。 |
| **Cognitive Core** | **DeepSeek-V3** | (经由 OpenAI SDK) 极高性价比的云端推理引擎，适合高频日志分析。 |
| **Perception** | **MSS / Win32 API** | 毫秒级屏幕差分与句柄获取，极低资源占用。 |
| **OCR Engine** | **Windows.Media.Ocr** | 操作系统内置 OCR，离线、免费、隐私安全。 |
| **Data Storage** | **SQLite** | 单文件结构化存储，数据主权完全在本地。 |

---

## 5. 开发路线图 (Development Roadmap)

### Phase 0: 基础设施 (Infrastructure)
* [ ] 定义核心数据模型 (`TaskState`, `Event`)。
* [ ] 配置 SQLite ORM 与数据库迁移。
* [ ] **验证 Tailscale + WebSocket P2P 连通性。**

### Phase 1: 感知与本地状态 (Sentinel & L1)
* [ ] 实现 `WindowWatcher` (句柄) 与 `InputMonitor` (活跃度)。
* [ ] 移植 MineContext 核心算法，实现 `Raw Events -> TimeWindow` 的聚合。
* [ ] 输出：一个能生成本地 JSON 日志的 CLI 工具。

### Phase 2: UI 原型 (Dashboard)
* [ ] 搭建 Flet 主框架。
* [ ] 实现时间轴组件可视化。
* [ ] 实现系统托盘与后台驻留逻辑。

### Phase 3: 云端大脑 (Brain)
* [ ] 集成 OpenAI SDK (适配 DeepSeek)。
* [ ] 编写 Gatekeeper (去敏/拦截) 逻辑。
* [ ] Prompt Engineering：让 AI 学会阅读 JSON 并输出心理分析。

### Phase 4: 多端同步 (Sync)
* [ ] 引入 `y-py`。
* [ ] 将 SQLite 数据层改造为支持 CRDT 的存储层。
* [ ] 联调多端数据合并逻辑。

---

## 6. 传感器测试 UI (Sensor Test UI)

传感器测试界面已切换为 Electron 方案，入口与启动方式以 Electron 侧说明为准。

### 日志规范

* 日志统一存放在 `data/logs/`，最多使用一层子目录，子目录名取自 `contexgo/` 下脚本路径的第一层。
* 命名规则：日志文件名必须与脚本文件名一致（不含扩展名），例如：
  * `contexgo/chronicle/sensors/focus.py` → `data/logs/chronicle/focus.log`
  * `contexgo/chronicle/assembly/chronicle_gate.py` → `data/logs/chronicle/chronicle_gate.log`
  * `contexgo/main.py` → `data/logs/main.log`
* 代码需自动创建目录层级（`os.makedirs(os.path.dirname(log_path), exist_ok=True)`）。
* 滚动与保留：单文件大小 `5 MB` 触发滚动，保留最近 `5` 个历史文件（`rotation="5 MB"`, `retention=5`）。

## 7. 协议 (License)

**apache 2.0**
