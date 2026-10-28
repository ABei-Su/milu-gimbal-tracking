# 人体测试架构
camera/YOLO11 子进程 → 最新人体框队列(容量1) → TargetStream → VisualServo → Gimbal → F32C。
唯一主进程拥有执行器；算法复制自原版0.4控制核心。仅识别类别改为person，模型指向官方板载COCO模型。
模型双缓冲关闭以确保检测和时间戳对应。控制20Hz，视觉独立运行；过期帧、空帧与失去目标使参考重建。光源只有关断接口，拒绝开启，不提供paper入口。
详见 docs/adr/0001-person-test.md、hardware-contract.md 和 state-machine.md。日志3×1MB、单帧队列、不传图像，无Flash或OTA写入。实际内存/帧率/SDK/板修订均为实测TBD。

0.2.0: head_model selects genuine AX face models (YOLO face/Retinaface/FaceDetector) with local weight checks before motors start. Existing person backend remains explicit compatibility mode, never fallback for face. homing converts mechanical zero to cumulative target, limits travel/rate/time, and supplies fixed origin. Target loss holds a captured setpoint. See ADR 0005.

0.2.1: 用户确认机械可转360度；跟随限位改为双轴±90度，最短路径回零允许180度/45秒。先回零后启动视觉，启动不主动失能；故障及退出仍失能。实际负载回正待板端验收。

0.2.3 当前部署：home_enabled=false，startup_pitch_lift=10；STARTING→HOMING执行相对抬头（2号减10度，1号原地保持），到位→READY并启动视觉。该点仅为软件跟随原点，不是水平零位。速率3度/秒，原超时和偏差保护保留；每次运行重复相对动作。详见ADR0007。

0.2.7：用户授权启动相对抬头45度，速率6度/秒，1号保持。到位后开启视觉并等待人脸，不自动扫描。控制每轮先查询反馈再取最新检测消息；视觉启动期间也查询反馈。其余轨迹参数不变，详见ADR0011。

0.3.0：视觉先启动，首个新鲜帧就绪后允许启动搜寻。HOMING相对抬头分支可由有效人脸提前结束并捕获实测跟随原点；取消/超时/视觉错误走既有故障清理。机械回零分支不受检测打断。左右逐轴约束与上下独立，详见ADR0013。

0.3.3：跟随左右范围改为相对捕获起点±180度，上下±90度；到限位保持该轴边界，可反向退出，另一轴独立运行。angle_limit_axes报告具体角度限位轴，修复目标饱和漏报。撤回40ms请求滤波，保留原运动整形和搜索90度。原点不自动重置，不是无限旋转；板端验收待完成。详见ADR0016。

当前回退部署0.3.1：取消请求滤波，搜索60度提前识别停止、两轴跟随±90度，其余恢复ADR0014。此记录覆盖0.3.2/0.3.3部署说明，见ADR0017。

当前部署：用户要求取消左右软件角度限位，yaw_limit_enabled=false；不在±90/180/360度停转。不改变当前平滑控制参数，上下±90度、启动搜索60度及提前识别停止保持。旧配置默认仍启用限位；设置true可恢复yaw_limit。输入有限数、通信超时和F32C累计角度协议范围检查保留；不允许无限数指令。连续绕转可能缠绕外接线。主机135项测试通过，实机待验收。详见ADR0018。


当前左右温和调优（yaw-gentle-20261013）：yaw_max_lead=6度，yaw_gain_multiplier=1.08；其余平滑参数、上下控制、启动60度及人脸提前结束保持。左右角度限位仍关闭。日志lead_deg为目标减实际角度，不是限位事件计数。更大领先可能增加超调，实机平滑/延迟改善待验证。恢复yaw_max_lead=0、yaw_gain_multiplier=1即回到本次调优前响应。完整离线检查137项通过，见ADR0019。

