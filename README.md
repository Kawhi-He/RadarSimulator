# Radar Target Simulator

本项目提供一个统一的 Python 入口，用于控制 R&S 雷达目标模拟器，并在自动模式下联动 Quectel 点云监控上位机完成录制和结果分析。

This project provides one unified Python entry point for controlling an R&S radar target simulator. In auto mode it also drives the Quectel radar recording tool and writes analysis logs next to each recorded `frame.txt`.

## 快速开始 | Quick Start

```bash
python radar_target_simulation.py
```

常用命令：

```bash
python radar_target_simulation.py --profile xiaoniu --mode auto
python radar_target_simulation.py --profile aima --mode manual
python radar_target_simulation.py --profile xiaoniu --mode auto --record-seconds 10
python radar_target_simulation.py --ip 10.66.156.52
python radar_target_simulation.py --help
```

依赖安装：

```bash
pip install RsInstrument psutil pywinauto pywin32
```

## 入口参数 | CLI Options

| 参数 | 说明 |
| --- | --- |
| `--profile` | 选择车型配置，当前支持 `xiaoniu` 和 `aima`。 |
| `--mode` | `auto` 自动录制并分析，`manual` 只控制模拟器，手动停止。 |
| `--ip` | R&S 模拟器 IP，默认来自 `radar_simulator.DEFAULT_IP`。 |
| `--source` | AREG source index，默认 `1`。 |
| `--mapping-channel` | 启动时执行 level adjust 的 mapping channel，默认 `A1`。 |
| `--skip-level-adjust` | 跳过启动时的 AREG level adjust。 |
| `--t-res` | 动态场景刷新间隔，默认 `0.1s`。 |
| `--record-seconds` | 默认录制时长。部分场景会按测试规则自动覆盖该值。 |

## 场景选择 | Scenario Input

选择车型后输入场景编号：

| 输入 | 含义 |
| --- | --- |
| `1`, `2`, ... | 动态目标场景。 |
| `F1`, `F2`, ... | 静态单目标场景。 |
| `M1`, `M2`, ... | 多目标场景。 |
| `Q` | 退出。 |

`xiaoniu` 当前主要专项场景：

| 场景 | 说明 |
| --- | --- |
| `F1-F4` | `RCS=10dBsm, speed=10m/s`，距离分别为 `5m/10m/15m/20m`。 |
| `F5-F26` | `RCS=10dBsm, range=10m`，速度从 `-57m/s` 到 `44m/s`。 |
| `M1` | 两固定目标，`-10km/h`，距离 `10m` 与 `14m`，用于距离分辨率。 |
| `M2` | 两固定目标，`range=10m`，速度 `-10km/h` 与 `-20km/h`，用于速度分辨率。 |
| `D7` | `RCS=20dBsm, range=10m`，速度扫描 `-57m/s` 到 `44m/s`。 |
| `D13-D15` | `RCS=10dBsm, 30m -> 2m` 接近场景，速度分别为 `120/60/20km/h`。 |

## 自动录制 | Auto Recording

自动模式会先准备 Quectel 点云监控上位机：

1. 如果上位机没有启动，脚本会启动软件，然后执行 `Communication -> CAN -> Open Device -> Open CAN`。
2. 如果上位机已经启动且录制按钮可用，脚本会跳过启动和 CAN 初始化，直接进入录制。
3. 每次录制结束后，脚本会把新目录重命名为带时间戳、车型、场景编号和场景描述的目录。

录制时长规则：

| 场景类型 | 录制时长 |
| --- | --- |
| 静态单目标 `F*` | 固定录制 `10s`。 |
| 远离动态目标 | 自动覆盖至少 `3` 个完整周期。 |
| 接近动态目标 | 自动覆盖至少 `3` 个完整周期。 |
| `D7` 测速范围 | 自动覆盖完整速度扫描窗口。 |
| `M1/M2` 分辨率 | 每个二分法测试点录制 `5s`。 |

## 输出文件 | Output Logs

每次自动录制后，目录内至少会有 `frame.txt`。满足专项分析条件时还会生成对应结果文件：

| 文件名 | 场景 | 内容 |
| --- | --- | --- |
| `fixed_target_analysis_*.log` | 静态单目标 `F*` | 连续性、距离或速度误差、角度显示、点云数量、报警摘要。 |
| `max_distance_analysis_*.log` | 远离动态目标 | 最远丢失距离、最远检测距离、横向稳定性、点云数量、报警信息。 |
| `approaching_target_analysis_*.log` | 接近动态目标 | 接近轨迹摘要、点云数量、基于目标对象的报警区间。 |
| `speed_sweep_analysis_*.log` | `D7` 测速范围 | 测速覆盖范围、缺失速度桶、点云数量。 |
| `multi_target_resolution_analysis_*.log` | `M1` | 距离分辨率二分法结果。 |
| `multi_target_speed_resolution_analysis_*.log` | `M2` | 速度分辨率二分法结果。 |

日志采用中英双语格式，例如：

```text
连续性检查 | Continuity check: ...
最终结论 | Overall result: PASS
```

## 分析规则 | Analysis Rules

### 静态单目标 `F*`

`xiaoniu F1-F4`：

- 点云连续，无间断，无连续 `3` 帧丢失。
- 读取距离与模拟器设置距离误差在 `+/-0.4m` 以内。
- 点云数量应等于 `虚拟目标数 + 1 个金属目标`，单目标场景期望为 `2`。

`xiaoniu F5-F26`：

- 点云连续，无间断，无连续 `3` 帧丢失。
- 读取速度与模拟器设置速度误差在 `+/-0.1m/s` 以内。
- 点云数量应等于 `2`。

角度说明：

- `xiaoniu` 只关注水平角 `AngleAZ`。
- `AngleAZ` 原始值按弧度处理，日志中只显示转换后的度数。
- `AngleEL` 暂不参与判定。

### 多目标 `M1/M2`

目标数量按 `frame.txt` 中 `[Object]` 段的行数判断：

- `[Object]` 下 `2` 行表示识别出 `2` 个目标。
- `[Object]` 下 `1` 行或 `0` 行表示 `Object目标数<2`。

`M1` 距离分辨率：

- 固定目标 1 在 `10m`。
- 通过二分法缩小目标 2 的距离，目标 2 从 `14m` 往 `10m` 靠近。
- 记录两目标合并成一个目标前的最小距离差。
- 测试标准：无连续 `3` 帧 `Object目标数<2`，距离分辨率 `<0.85m`。

`M2` 速度分辨率：

- 固定目标 1 为 `-10km/h`。
- 通过二分法调整目标 2 的速度，从 `-20km/h` 往 `-10km/h` 靠近。
- 记录两目标合并成一个目标前的最小速度差。
- 测试标准：无连续 `3` 帧 `Object目标数<2`，速度分辨率 `<0.2m/s`。

多目标场景点云数量期望为 `3`，即 `2` 个虚拟目标加 `1` 个金属目标。

### 动态远离目标

远离动态场景会输出：

- 每个周期的目标轨迹、丢失帧、最远检测距离和最远丢失距离。
- 横向稳定性摘要。
- 点云数量检查。
- 报警信息。

横向稳定性基于目标轨迹的 `AngleAZ` 和横向偏移统计，日志会给出每个周期的 `stable`、`noticeable jitter` 或 `left-right crossing`。

### 动态接近目标

接近动态场景会输出：

- 每个周期的起始检测距离、最近检测距离、速度和横向稳定性。
- 点云数量检查。
- 报警区间。

报警区间使用 `[Object]` 目标信息，不使用 `[Point]` 点云距离：

- `Object.DistLong` 作为纵向报警距离。
- `Object.VreLong` 作为报警速度。
- 如果模拟器切换周期时临时出现两个目标，脚本只匹配当前主轨迹对应的那个目标，忽略另一个过渡目标。

报警类型：

| `AlarmType` | 含义 |
| --- | --- |
| `0` | 不报警 |
| `1` | 左侧报警 |
| `2` | 右侧报警 |
| `3` | 后方报警 |

### `D7` 测速范围

`xiaoniu D7` 会验证测速正确范围是否覆盖 `-57m/s` 到 `44m/s`：

- 按 `1m/s` 作为速度桶。
- 需要覆盖完整区间且中间无缺失速度桶。
- 点云数量期望为 `2`。

## 代码文件 | Source Files

| 文件 | 说明 |
| --- | --- |
| `radar_target_simulation.py` | 主入口、交互菜单、自动录制流程、各类报告生成。 |
| `radar_scenarios.py` | `xiaoniu` 和 `aima` 的场景配置。 |
| `radar_simulator.py` | R&S SCPI 控制封装，支持动态、静态、多目标和在线调整目标参数。 |
| `radar_recording.py` | Quectel 上位机准备、录制、目录识别和重命名。 |
| `radar_can_tool.py` | Quectel 上位机 Windows UI 自动化。 |
| `detect_loss.py` | `frame.txt` 解析和所有分析算法。 |
| `radar_scpi_demo.py` | 最小 SCPI 示例。 |

## 注意事项 | Notes

- 旧日志不会自动更新。修改分析逻辑后，需要重新录制或重新触发分析才会生成新格式日志。
- `frame.txt` 中 `[Point]` 表示点云点，`[Object]` 表示目标对象。多目标分辨率和动态报警优先使用 `[Object]`。
- 点云数量规则来自暗箱测试口径：理论点云数量为 `虚拟目标数 + 1 个金属目标`。
- 自动模式依赖 Windows UI 自动化，运行前请确认 Quectel 上位机路径和控件 ID 与当前版本一致。
