# 状态与故障
Gimbal: NEW --start--> STARTING --有效反馈--> READY；启动/运动/反馈失败进入 FAULT；close 进入 CLOSED，重复close幂等。仅READY允许运动，FAULT不自动恢复。两轴命令先验证；发送失败尝试双轴失能。
视觉队列最新帧覆盖旧帧，拒绝重复、倒序和过期观测；空检测立即清目标。目标丢失、切换、长控制间隔重建参考，停止追旧目标。弱框仅在强框新鲜期限内续跟。
应用 observe 不访问执行器；track 关闭光源并运行电机。paper为非法模式，在硬件访问前拒绝。LaserOutput.set(True)先输出关闭电平再抛错；没有允许点亮状态。
退出或视觉子进程异常：独立尝试关光源、双轴失能、关闭串口、退出子进程；不在异常后自动恢复。物理断线/断电/进程强杀不受Python清理保证。

0.2.0: STARTING -> HOMING when home_enabled, -> READY only after five consecutive readings within 0.3 degrees at the target. Cancellation, timeout, missing feedback, excessive initial travel or following error -> FAULT and best-effort disable. Legacy home_enabled=false preserves position capture for offline compatibility. HOMING is bounded to 45s by deployment config; cancellation checked every iteration. Startup completes homing before starting the vision worker. Model metadata validation still precedes actuation. Vision startup has a separate 45-second deadline.
Target loss: first missing/stale observation captures HOLD angle; subsequent missing observations preserve that setpoint even if gravity changes measured angle. Reacquisition rebases reference once before resuming. Feedback bounds and startup faults still apply.

0.2.3 当前部署：home_enabled=false，startup_pitch_lift=10；STARTING→HOMING执行相对抬头（2号减10度，1号原地保持），到位→READY并启动视觉。该点仅为软件跟随原点，不是水平零位。速率3度/秒，原超时和偏差保护保留；每次运行重复相对动作。详见ADR0007。

0.2.7：用户授权启动相对抬头45度，速率6度/秒，1号保持。到位后开启视觉并等待人脸，不自动扫描。控制每轮先查询反馈再取最新检测消息；视觉启动期间也查询反馈。其余轨迹参数不变，详见ADR0011。

0.2.8 用户要求启动相对抬60度、速率仍6度/秒；俯仰跟随参数保持，后续重点调优底部左右轴。详见ADR0012。

0.3.0：视觉先启动，首个新鲜帧就绪后允许启动搜寻。HOMING相对抬头分支可由有效人脸提前结束并捕获实测跟随原点；取消/超时/视觉错误走既有故障清理。机械回零分支不受检测打断。左右逐轴约束与上下独立，详见ADR0013。

0.3.1 两轴共用平滑参数；反馈偏差恢复仅作用于相应轴，另一轴保持连续更新。丢目标/故障退出规则不变，详见ADR0014。

0.3.2 搜寻最大相对90度，途中检测提前终止；两轴请求平滑40ms，超时和故障规则不变，详见ADR0015。

0.3.3：跟随左右范围改为相对捕获起点±180度，上下±90度；到限位保持该轴边界，可反向退出，另一轴独立运行。angle_limit_axes报告具体角度限位轴，修复目标饱和漏报。撤回40ms请求滤波，保留原运动整形和搜索90度。原点不自动重置，不是无限旋转；板端验收待完成。详见ADR0016。

当前回退部署0.3.1：取消请求滤波，搜索60度提前识别停止、两轴跟随±90度，其余恢复ADR0014。此记录覆盖0.3.2/0.3.3部署说明，见ADR0017。

当前部署：用户要求取消左右软件角度限位，yaw_limit_enabled=false；不在±90/180/360度停转。不改变当前平滑控制参数，上下±90度、启动搜索60度及提前识别停止保持。旧配置默认仍启用限位；设置true可恢复yaw_limit。输入有限数、通信超时和F32C累计角度协议范围检查保留；不允许无限数指令。连续绕转可能缠绕外接线。主机135项测试通过，实机待验收。详见ADR0018。

