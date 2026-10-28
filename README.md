# 麋鹿识别与双轴无刷云台跟随 · MaixCAM2

MaixCAM2 视觉识别 + WHEELTEC F32C 双轴无刷电机控制项目，包含麋鹿检测、热成像实验版，以及已封板的人脸跟随 v1.0。

## 运行哪个版本
| 目录 | 用途 | 入口与状态 |
| --- | --- | --- |
| `person_follow_test/` | **人脸识别与云台跟随 v1.0** | MaixVision 打开整个目录，运行项目；入口 `main.py`；已有用户实机反馈 |
| 仓库根目录 | 原麋鹿识别与云台控制原型 | `main.py`，默认 observe；详细说明见 [原项目说明](PROJECT_README.md) |
| `thermal_version/` | MLX90640 热成像组合实验版 | 见该目录 README，硬件验收状态以其文档为准 |
| `trained_model/` | 700 多张人工标注图训练的新麋鹿模型 | PT/ONNX 已评估，尚需 AX 编译；**未接替原程序的模型** |

## 人脸云台跟随 v1.0（当前实机使用版）
1. 下载仓库 ZIP 并解压，或 `git clone https://github.com/ABei-Su/milu-gimbal-tracking.git`。
2. MaixVision 选择“打开文件夹/项目”，打开 `person_follow_test/`。
3. 连接 MaixCAM2，确保板端存在兼容的人脸模型，点击 **运行项目**。
4. 启动日志应显示 `[BUILD] v1.0.0 | yaw-gentle-v2 frozen`。

串口接线：MaixCAM2 **B0（UART2 TX）→ 电机通信板 RX**，**B1（UART2 RX）→ TX**，**GND → GND**；115200、8N1。
F32C 电机使用独立电源，电机 1 为左右轴、电机 2 为俯仰轴。电机电源不得接入 MaixCAM2 信号引脚。
人脸模型采用板端兼容的 `yolo11s_face.mud` 等 AX 模型，查找与选择规则见 [人脸版本说明](person_follow_test/README.md)；仓库不含人脸权重。

该封板版启动相对抬头上限 60°，发现有效人脸提前结束；左右软件角度限位已关闭，上下 ±90°。
控制参数及源码按本地封板版复制。连续绕转的线材余量、负载温升、长期运行等仍需现场验证。

## 麋鹿模型
根目录 `models/milu*.axmodel` 是原先机器候选标注训练的**旧原型模型**，供原程序联调；不是新人工标注模型。
新人工标注模型位于 `trained_model/weights/best.pt` 和 `best.onnx`，测试集 mAP@0.5 为 86.29%、mAP@0.5:0.95 为 43.51%。
新模型尚未生成 `.axmodel`、未接入现有云台程序。其数据、指标与局限见 [模型说明](trained_model/README.md)。

## 文档与验证
架构、硬件约定、状态机、ADR、接线及部署说明在各版本 `docs/` 与 `ARCHITECTURE.md` 中。
Python 主机验证：安装 `requirements-dev.txt` 后，在相应版本目录执行 `python tools/verify.py`。
本仓库保留原有开发文档与版本记录；存在历史状态描述时，以对应版本 README 顶部及实际 config.json 为准。

## 公开范围与许可
包含项目源码、配置、测试、工具、部署说明、旧 AX 原型模型及新训练 PT/ONNX 模型。
不包含原始照片、聊天附件、厂家资料压缩包、个人调试日志、环境和账号凭据。
自编代码和派生模型按根目录 AGPL-3.0 提供；上游来源见 [模型许可说明](trained_model/NOTICE.md)，依赖保留各自许可。
