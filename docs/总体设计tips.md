保持 chronicle/protocol 仅存放原始物理信号定义。
/CONTEXGO
1.  chronicle/             # [积木-编年史] L1 核心：负责物理信号的采集与初步组装
    1.1  assembly/         # 组装引擎：将离散信号切片并打包成 FocusSpan/TimeWindow
    1.2  protocol/         # 物理协议：定义 L1 层的事件模型和窗口数据结构 (单真源)
    1.3  sensors/          # 传感器集群：抄作业区，包含键鼠、窗口句柄、视觉抓取等
    1.4  __init__.py       # 包初始化：对外暴露组装器接口
2.  data/                  # [物理存储中枢] 独立于代码的持久化数据文件夹 (Git 已忽略)
    2.1  gallery/          # 视觉档案库：按日期存储的滚动截图 (.webp)
3.  sync/                  # [积木-同步中枢] M2：负责物理存储管理与多端同步逻辑
    3.1  gateway.py        # 统一存储网关：所有模块读写数据库的唯一出口
    3.2  __init__.py       # 包初始化：暴露 SyncGateway 单例
4.  brain/                 # [积木-认知] M3：负责离线推理、记忆体管理与信号清洗
    4.1  __init__.py       # 包初始化
5.  nexus/                 # [积木-交互] M4：人机交互界面与实时反馈哨兵
    5.1  __init__.py       # 包初始化
6.  infra/                 # [公共积木] 基础设施：全局通用的工具与底盘
    6.1  config.py         # 配置管理：定义数据路径 (data/) 和传感器阈值
    6.2  __init__.py       # 包初始化
7.  docs/                  # 项目文档库：存放设计协议与架构 Tips
    7.1  L1设计文档.md      # L1 协议详细规范
    7.2  总体设计tips.md    # 架构设计决策记录
8.  .gitignore             # Git 忽略配置：已确保 data/ 不会被上传
9.  LICENSE                # 项目授权协议
10. main.py                # 组装底板：程序的启动入口，负责挂载各模块积木
11. pyproject.toml         # 包管理配置：定义项目依赖与模块化安装范式
12. README.md              # 项目愿景与核心逻辑说明