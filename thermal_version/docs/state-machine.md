# 运行状态

测温入口的选择、融合、失效与清理状态见 [thermal-state-machine.md](thermal-state-machine.md)。下面保留原模式状态机。

版本0.3，单进程独占执行器；相机子进程只投递观测。配置无持久状态迁移，旧会话不复用。

## Gimbal

| 原状态 | 事件/条件 | 新状态/动作 |
| --- | --- | --- |
| NEW | start | STARTING：等待上电、失能、查询角度、原地配置 |
| STARTING | 两轴反馈有效 | READY：建立软件零点 |
| STARTING/READY | 超时、越限、部分写入或IO异常 | FAULT：尝试两轴失能，记录原因，异常上抛 |
| READY | poll/move合法 | READY：刷新反馈/更新目标 |
| 任意未关闭状态 | close | CLOSED：失能、关闭UART |
| CLOSED | close重复 | CLOSED：幂等，无输出 |

start只接受NEW；poll/move只接受READY。FAULT不自动重试，需退出重启和重新获取反馈。无后台控制写入者；跨轴发送非原子，失败以双轴失能补偿。序号不可用，反馈只能ID/类型匹配与清缓冲，硬件协议限制明确保留。

## 平滑参考恢复事件

每轴居中采用进入deadband、退出deadband+hysteresis回差。目标失效/过期、generation变化、控制间隔>max_control_gap、反馈突变或倒序帧触发参考重建，清除速度/加速度与旧滤波。常规运动参考的速率/加速度/加加速度受限；边界保护和重建优先于连续性。没有新增可跨重启恢复的持久化状态。

## LightGate

DISARMED（非paper）不产生输出。paper初态WAITING；资格连续满足dwell进入PULSE；脉冲到期进入COOLDOWN，再回WAITING。居中资格还要求软件参考速度≤settle_rate。资格撤销或generation变化即时撤销输出；FAULT终态不恢复；时钟倒退进入FAULT。每次控制IO前物理关灯，再按状态结果决定输出，因此0.15秒表示最大许可窗口而非严格连续点亮时长。

## 视觉

最新帧覆盖旧帧；重复/倒序/过期帧不作为新观测。目标在stale_after内可复用，空帧立即清除；lock_timeout后允许重新选择并变更generation。关联半径内优先保持原目标，多目标为ambiguous，禁止光点。视觉进程退出/启动超45秒导致整机退出和清理。

legacy tracking.Tracker 的SEARCHING/TRACKING/LOST/STOPPED/FAULT仅用于离线仿真，不用于板端执行器状态。
