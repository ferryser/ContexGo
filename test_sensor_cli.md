# test_sensor_cli 使用指南

## 目标

`test_sensor_cli.py` 是一个面向 Windows + Python 3.12 的 GraphQL CLI：

- 读取 `/graphql` 的 sensor 状态（Query.sensors）。
- 启停/注册/注销/批量启停 sensor（Mutation.toggleSensor / bulkAction / registerSensor / unregisterSensor）。
- 订阅 `logStream`，并**在消费端丢弃 1 秒前的日志**，以保证实时性。
- 提供 `serve` 指令启动后端并订阅日志，仅接收当前命令链路中的日志。
- 使用**多路复用连接池**复用 HTTP 连接，减少 Windows 的套接字占用。

## 环境准备

- Windows
- Python 3.12
- 后端已启动并暴露 GraphQL：`http://127.0.0.1:35011/graphql`

> 订阅需要 `websockets` 依赖，通常随 `strawberry-graphql[fastapi]` 安装。若缺失：
> ```powershell
> pip install websockets
> ```

## 启动后端

```powershell
python -m contexgo.main
```

默认监听 `http://127.0.0.1:35011/graphql`。

## 使用 CLI 启动后端（serve）

`serve` 指令会在同一终端中启动 `contexgo/main.py`，并将子进程的 stdout/stderr 直接输出到 CLI 窗口。
同时，CLI 会在后台订阅 `logStream`，仅输出**命令启动之后**产生的日志；当命令结束时，自动取消订阅。

### 基本用法

```powershell
python .\test_sensor_cli.py serve
```

### PID 存根与 Ctrl+C

`serve` 启动后会打印子进程 PID，例如：

```
Started main.py (pid=12345)
```

当用户按下 `Ctrl+C`：

1. CLI 捕获 `KeyboardInterrupt`；
2. CLI 向子进程发送 `SIGINT`；
3. 子进程执行 `logger.py` 预期的资源回收逻辑并退出；
4. CLI 等待子进程退出并关闭订阅。

### 日志订阅范围

`serve` 模式下的日志订阅仅限当前命令生命周期：

- 只显示命令启动**之后**的日志；
- 命令退出后立即取消订阅，不会继续接收其他日志广播；
- 如果未安装 `websockets`，会跳过 `logStream` 订阅，但 stdout/stderr 仍会被转发。

## 常用命令示例（端口固定为 35011）

> 所有示例均以 `http://127.0.0.1:35011/graphql` 为目标地址。

### 1) 查询全部 sensor 状态

```powershell
python .\test_sensor_cli.py sensors
```

### 2) 启动 / 停止 / 切换 sensor

```powershell
python .\test_sensor_cli.py start window_focus
python .\test_sensor_cli.py stop window_focus
python .\test_sensor_cli.py toggle window_focus
```

### 3) 批量启停

```powershell
python .\test_sensor_cli.py bulk-start window_focus input_metric
python .\test_sensor_cli.py bulk-stop window_focus input_metric
```

### 4) 注册 / 注销 sensor

```powershell
python .\test_sensor_cli.py register window_focus --sensor-id window_focus
python .\test_sensor_cli.py unregister window_focus
```

带配置注册（JSON）：

```powershell
python .\test_sensor_cli.py register window_focus --sensor-id window_focus --config '{"capture_interval": 0.5}'
```

### 5) 订阅日志（消费端过滤 1 秒前日志）

```powershell
python .\test_sensor_cli.py log-stream
```

自定义最大延迟窗口：

```powershell
python .\test_sensor_cli.py log-stream --max-age-seconds 0.5
```

### 6) 订阅 sensor 状态变化（可选）

```powershell
python .\test_sensor_cli.py status-stream
```

### 7) 使用多路复用连接池

```powershell
python .\test_sensor_cli.py --pool-size 2 sensors
```

- `--pool-size`：控制复用连接数（默认 2）。
- `--timeout`：HTTP / WebSocket 超时时间（默认 10 秒）。

## 常见问题

1. **订阅时报错**：请确认已安装 `websockets`。
2. **日志过滤**：CLI 仅打印时间戳在 1 秒内的日志（可通过 `--max-age-seconds` 调整）。
3. **端口不一致**：此指南固定为 `35011`，确保后端监听端口与 CLI 一致。
4. **serve 无日志**：确认 `websockets` 已安装，或查看 stdout/stderr 输出是否正常。
