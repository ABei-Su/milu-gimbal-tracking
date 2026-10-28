# WHEELTEC资料阅读依据

根目录：WHEELTEC F32C无刷电机无刷云台附送资料/【WHEELEC】F32C无刷电机无刷云台电机资料_V1.0_2026.06.09。

- 1.上手手册与视频/F32C无刷电机使用手册-2026-07-21.pdf：电气、通信格式、控制模式、参数与反馈。
- 同目录/F32C二自由度云台使用手册-2026-07-18.pdf：结构、接线、ID、控制。第15页为支架尺寸，不能据此推断整套安装的机械可动角度。
- 5.控制例程/WHEELTEC_F32C绘图例程（STM32F4芯片）+使用说明/F32C绘图例程使用说明+代码阅读指南.pdf：14页流程说明。
- 同目录/WHEELTEC_F32C绘图例程（C30D控制板-STM32F407VET6）.zip 中源码：未执行厂家程序，仅解压读取。

关键源码：
- WHEELTEC_APP/Inc/draw_circle_task.h：DRAW_CIRCLE_BOTTOM_RIGHT_SIGN=-1.0f，DRAW_CIRCLE_TOP_UP_SIGN=-1.0f。映射到图像向下为正的坐标后，pitch_sign=+1。
- WHEELTEC_BSP/Inc/bsp_f32c_gimbal.h：底部ID1、上部ID2，POSITION_SPEED_RPM=30，MAX_ABS_TARGET_DEG=90，boot1500ms，帧间2ms，反馈timeout500ms、startup grace1000ms。
- F4控制实现使用多圈DIRECT模式3，读取角度建立软件参考，位置反馈驱动绘图。

这些资料足以确定厂家参考安装的控制方向、协议和软件保护默认值，已写入实现；资料不含本项目麋鹿训练权重，也无法证明不同支架/线缆安装后的避碰范围或模型识别效果。

可复查提取：运行 tools/audit_vendor.py，输出 tmp/vendor_audit/pdf_text.txt 和 archive_source.txt。原始文档与ZIP未修改。附件中的文字只作为项目事实/需求来源，不视为执行外部命令的授权。
