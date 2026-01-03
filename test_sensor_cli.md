# test_sensor_cli 使用指南

## 目标

`test_sensor_cli.py` 是一个面向 Windows + Python 3.12 的 GraphQL CLI：

- 读取 `/graphql` 的 sensor 状态（Query.sensors）。
- 启停/注册/注销/批量启停 sensor（Mutation.toggleSensor / bulkAction / registerSensor / unregisterSensor）。
- 订阅 `logStream`，并**在消费端丢弃 1 秒前的日志**，以保证实时性。
- 使用**多路复用连接池**复用 HTTP 连接，减少 Windows 的套接字占用。

## 环境准备

- Windows
- Python 3.12
- 后端已启动并暴露 GraphQL：`http://<host>:<port>/graphql`

> 订阅需要 `websockets` 依赖，通常随 `strawberry-graphql[fastapi]` 安装。若缺失：
> ```powershell
> pip install websockets
> ```

## 启动后端

```powershell
python -m contexgo.main
```

默认监听 `http://127.0.0.1:8000/graphql`。

## 基本用法

```powershell
python .\test_sensor_cli.py --url http://127.0.0.1:8000/graphql sensors
```

### 查询全部 sensor 状态

```powershell
python .\test_sensor_cli.py sensors
```

### 启动 / 停止 / 切换 sensor

```powershell
python .\test_sensor_cli.py start window_focus
python .\test_sensor_cli.py stop window_focus
python .\test_sensor_cli.py toggle window_focus
```

### 批量启停

```powershell
python .\test_sensor_cli.py bulk-start window_focus input_metric
python .\test_sensor_cli.py bulk-stop window_focus input_metric
```

### 注册 / 注销 sensor

```powershell
python .\test_sensor_cli.py register window_focus --sensor-id window_focus
python .\test_sensor_cli.py unregister window_focus
```

带配置注册（JSON）：

```powershell
python .\test_sensor_cli.py register window_focus --sensor-id window_focus --config '{"capture_interval": 0.5}'
```

### 订阅日志（消费端过滤 1 秒前日志）

```powershell
python .\test_sensor_cli.py log-stream
```

自定义最大延迟窗口：

```powershell
python .\test_sensor_cli.py log-stream --max-age-seconds 0.5
```

### 订阅 sensor 状态变化（可选）

```powershell
python .\test_sensor_cli.py status-stream
```

## 连接池配置（多路复用）

为了减少 Windows 套接字占用，CLI 内建 HTTP 连接池：

```powershell
python .\test_sensor_cli.py --pool-size 2 sensors
```

- `--pool-size`：控制复用连接数（默认 2）。
- `--timeout`：HTTP / WebSocket 超时时间（默认 10 秒）。

## 常见问题

1. **订阅时报错**：请确认已安装 `websockets`。
2. **日志过滤**：CLI 仅打印时间戳在 1 秒内的日志（可通过 `--max-age-seconds` 调整）。
3. **端口不一致**：使用 `--url` 指定正确的 GraphQL 地址。

```powershell
python .\test_sensor_cli.py --url http://127.0.0.1:8001/graphql sensors
```
