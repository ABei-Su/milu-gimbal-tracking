# 麋鹿二维云台实验系统（MaixCAM2）

已实现 Word 第一阶段的软件链路：相机采集 → 麋鹿框检测 → 目标关联 → Yaw/Pitch 反馈闭环 → MOS 纸靶光点指示。默认运行只识别的 observe 模式。原 Word、Excel 和 WHEELTEC 资料保持不变。

**先读 [部署与接线](docs/deployment.md)**。程序上传到 **MaixCAM2**，F32C 保留原厂固件；不需要把 Python 烧进电机或额外 STM32。项目不是机械鹿整机固件。

模型已经使用公开麋鹿照片训练，随部署包提供 MaixCAM2 模型。训练标签来自机器候选框，尚未人工逐框验收，因此这是可联调原型，不是已经证明物种识别准确率的成品。无实物连接，实际帧率、跟踪精度、避碰角度和光点误差尚未测量；不宣称算法已达到全局最优。

## 目录

| 文件 | 用途 |
| --- | --- |
| main.py | 板端入口，默认 observe |
| config.json | 引脚、方向、限位、滤波、阈值、光点参数 |
| milu/vision.py | MaixPy 相机和 YOLO11 独立进程 |
| milu/targeting.py | 新鲜度、目标关联、平滑及有界视觉伺服 |
| milu/gimbal.py、f32c.py | 电机反馈状态机和已核对的厂商协议 |
| milu/maixcam2.py | UART/GPIO 与模型文件适配 |
| milu/light.py、runtime.py | 稳定判定、光点时序与运行协调 |
| models/ | 训练权重、NPU 模型、指标报告 |
| tools/ | 数据下载、训练、转换、校准、验证、打包 |
| tests/ | 协议、控制、故障、模拟板端集成测试 |
| docs/ | 接线、参数、模型、厂商依据及验收说明 |
| dist/milu_maixcam2.zip | 代码和板端模型部署文件包 |

## 0.4 识别连续性与打印图

新增有界弱置信度延续、线性候选选择与单次推理缓存评估；新目标/激光仍使用强门槛。结果、回退和待补充事项见 [优化说明](docs/recognition-upgrade.md)。6张A4打印图在 output/pdf/milu_A4_print_targets.pdf。模型权重本轮未改变，真实识别率仍待独立实拍验证。

## 0.3 平滑控制

新增浮点位移累积、每轴死区回差、加速度/加加速度整形与边界提前减速。旧配置可继续读取。升级和参数见 [平滑控制说明](docs/smooth-control.md)，对照指标见 [仿真报告](docs/smooth-benchmark.md)。

## PC 验证

```powershell
.venv/Scripts/python.exe tools/verify.py
.venv/Scripts/python.exe -m milu.simulate
```

新环境先安装 Python 3.11+，执行 `python -m pip install -r requirements-dev.txt`。训练环境独立，见 [模型说明](docs/model-training.md)。

## 板端运行

把部署包解压内容完整上传到板端同一目录，在该目录执行：

```sh
python3 main.py --mode observe
python3 -m milu.diagnose --jog-axis yaw --delta 1
python3 main.py --mode track --seconds 30
python3 main.py --mode paper --seconds 30
```

按顺序完成接线、单轴确认和光轴校准再进入 paper；具体步骤见部署说明。Ctrl+C 退出，正常退出/异常会尝试关灯、失能两轴。光点只用于 Word 中的纸靶或模型实验。

WHEELTEC 已核对默认值：下轴 ID1、上轴 ID2，多圈直通模式3，30 RPM，帧间2 ms，向右对应负角、图像向下对应正角。厂家 ±90° 是软件保护；首轮限位 ±10°，可在配置中修改，实际可动范围取决于安装。

兼容迁移：未来换 K230 时替换相机/NPU、UART/GPIO 和进程运行适配；纯协议和控制逻辑可复用。K230 的 kmodel 不能与 MaixCAM2 的 axmodel 互换。
