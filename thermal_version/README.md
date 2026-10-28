# 麋鹿跟踪 + 红外测温独立集成版

本目录是完整独立工程，已同步原版 0.4.0 的识别连续性与控制代码；本集成版版本0.3.0。原项目仍在上一级目录；运行与部署本目录不需要父目录代码。

**当前测温硬件为微雪 MLX90640-D55（55°×35°），已切换标准 I²C 驱动。** 用户停用前一款GD32串口板，因此无需再等待旧串口协议。触屏框选、眼周跟踪、平滑云台控制和温度处理逻辑保留。驱动尚未实机验收，RGB/IR对齐标定默认未确认。

新增识别连续性、评估效率及打印资料见 [本轮优化说明](docs/recognition-upgrade.md)。原模式共享最新控制核心，D55测温配置保留。

## 入口与部署

所有 Python 代码都运行在 **MaixCAM2**。F32C 电机保留厂家固件，热像仪保留厂家固件，不向这两者烧录本项目代码。

将 dist/milu_thermal_maixcam2.zip 解压后整个目录传到 MaixCAM2，例如 /root/milu_thermal。在该目录运行：

```sh
python -m thermo.preflight
python -m thermo.probe --frames 8 --timeout 15
python main.py
```

preflight 只检查能力，不驱动硬件。默认未标定会返回非零；PC上也缺板端SDK/模型。probe只检查红外传感器，具有15秒截止时间，不启动电机或相机。板上必须有支持 MixFormerV2 的 MaixPy 和 /root/models/mixformer_v2.mud 系统模型；本包不假装包含它。与原版 YOLO11 麋鹿模型不同，这是用户框选区域的跟踪模型，不是自动眼周识别模型。

MaixVision：打开本目录工程后运行 main.py；安装应用时使用本目录 app.yaml，其 ID 为 milu_thermal，不覆盖原 milu_tracker。系统烧录流程和电机原始接线见 docs/deployment.md、docs/wiring.md；测温新增连接限制见 docs/thermal-hardware.md。

保留原方案三个模式：

```sh
python main.py --mode observe
python main.py --mode track
python main.py --mode paper
```

原模式使用 config.json，测温模式使用独立 thermal_gimbal.json 和 thermal.json。测温与原模式分别启动，不同时争用相机/电机。测温入口始终关闭激光。paper 仍是原纸靶模式。

## 屏幕操作

1. 启动显示实时画面，TRACK OFF，不自动启动云台。
2. 拖动框选眼周；拖动期间冻结选择画面，松手后开始跟踪。
3. 点击 TRACK ON 启动云台跟踪；SELECT EYE 重新框选；EXIT 退出并清理。
4. 跟踪丢失后保持无效，需重新框选，不自动把其他物体当成原眼周。
5. 接入D55并完成标定后，满足居中、稳定、像素覆盖、新鲜温度等条件才显示温度；未标定/无有效数据时为 --。
6. 关闭跟踪、丢失目标、画面过期、传感器异常、换目标都会撤销当前温度。

英文屏幕标签避免依赖额外中文字库：Temp 为多帧 P90 结果；ROI max/avg 为当前筛选后 ROI 最大/平均温度；均为红外表面温度。没有真实输入时不显示模拟温度。

## 文件结构

| 文件/目录 | 用途 |
| --- | --- |
| main.py / thermal_main.py | 集成入口 / 测温入口 |
| base_main.py / milu/ | 完整原方案和已优化云台控制 |
| thermo/selection.py / ui.py | 触屏、MixFormerV2、实时显示 |
| thermo/temperature.py | 3×3/5×5 ROI、MAD异常点、P90、5–10帧融合、有效性状态机 |
| thermo/runtime.py | 执行器所有者、进程监控、超时和退出 |
| thermo/sensor.py / probe.py | 微雪D55的官方MaixPy I2C适配 / 独立限时检查 |
| thermal.json | 微雪D55：I2C6、55°×35°、8Hz刷新初调 |
| thermal_gimbal.json | 测温专用光轴/云台参数 |
| tests/test_thermal*.py | 离线测温验证 |
| docs/thermal-hardware.md | D55四线接法、资料包、板端检查与标定 |
| docs/thermal-validation.md | 检查证据与实机验收项目 |

不要把大鹿框当成眼周框。D55视场55°×35°，远处小眼周仍可能不足一个红外像素。程序有覆盖检查，但真正的光学分辨率、镜头 FOV、测量距离和表面温度精度仍需实测标定。标称 ±2℃不等于能判别微小体温变化。

## 开发检查

在本目录安装 requirements-dev.txt 后统一执行：

```sh
python tools/verify.py
python tools/package_app.py
```

实际板端帧率、内存、接线和温度精度尚未验收；PC 离线测试不等于已经烧录成功。
