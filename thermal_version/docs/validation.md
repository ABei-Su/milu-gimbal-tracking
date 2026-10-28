# 验证记录（2026-09-21）

当前交付为MaixCAM2实验代码、公开数据训练原型及已转换的NPU模型。原始资料未修改。未连接MaixCAM2/F32C，因此下列主机证据与实物验收明确分开。

## 已执行

| 检查 | 结果 |
| --- | --- |
| .venv/Scripts/python.exe tools/verify.py | Ruff格式、lint、语法/编译/卫生检查通过；70个unittest通过 |
| python -m milu.simulate | 理想闭环收敛、超时LOST，光源保持关闭 |
| tools/check_dataset.py | 92图、165候选框、68摄影者组，边界/文件/分组隔离通过 |
| tools/evaluate_detector.py | 阈值报告已生成，仅对机器候选标注 |
| tools/check_conversion.py | 三层原始检测头回解与原ONNX一致，最大绝对差0.0001357 |
| Pulsar2 6.0-lite / AX620E | NPU2和NPU1均完成编译及工具内仿真检查；不是板上实测 |

tests包含协议碎片/噪声/BCC、轴符号和限幅、目标失效/重获、10FPS视觉配20Hz控制、paper资格与脉冲、UART部分写/截止时间、配置/model路径、设备异常清理和运行器模拟集成。测试中的FAULT日志是故障注入预期结果。

最终模型：NPU 2,824,878字节，VNPU 3,130,758字节；哈希在models/artifacts.json。PC模型训练对开发测试候选框mAP50=0.8677，不是人工物种识别准确率。没有配置外部类型检查器或漏洞扫描器，不宣称完成这些检查。

## 尚需实物验收

记录板/镜头/SDK/电机固件版本，应用包SHA256、配置及接线照片；测供电极性/满电/低压支路，逐轴±1°验证方向和反馈。检查失能后的支撑、限位和线缆余量。

以实际打印靶完成各项：检测帧率与延迟分位数；各距离的漏检/误检；稳态像素误差与光点毫米误差；慢速移动跟踪；多目标禁光；丢目标、拔通信（断电接线原则下模拟）、坏帧、摄像头异常、退出和电源重启；至少30分钟温升、内存、CPU与日志容量。量化模型还需板端对照照片验证精度。

预算：队列1帧、UART每读≤256字节、残留解析≤8字节、日志≤3MB，控制目标20Hz；峰值RAM、WCET、NPU延迟为TBD。软件不保证强杀/系统死机的物理关断，也不保证任意负载和速度下达到最佳跟踪效果。

## 原Word需求对应

| 需求 | 实现 | 证据/剩余 |
| --- | --- | --- |
| 相机识别麋鹿、输出中心 | vision、原型模型、TargetStream | 数据/模型已生成，现场物种与靶材泛化待验 |
| 根据水平垂直偏差跟踪 | VisualServo、Gimbal、F32C | 离线/模拟集成通过，实物方向小角度确认 |
| 光点验证位置 | LightGate、MOS、calibrate_aim | 状态测试通过，实际光轴和MOS电平待验 |
| 模块测试→联合调试 | diagnose、三种mode、部署指南 | 实机按说明操作 |
| 后续机械鹿移植 | I/O与核心分层 | Word明确属于后续阶段，不含机械鹿步态/整机执行器固件 |

## 0.3 validation — 2026-09-22

Full tools/verify.py PASS: 85 tests, Ruff format/lint, syntax/build and hygiene. Four regressions failed on the frozen 0.2 controller before the fix. Eight SIL scenarios executed, moving scenarios checked across three seeds. See smooth-benchmark.md for improvements and tradeoffs. Actual F32C/board tests remain pending.
