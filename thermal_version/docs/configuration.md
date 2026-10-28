# 参数与调参顺序

所有角度为度，速度为度/秒，时间为秒，图像位置为0–1归一化；只有position_rpm是电机RPM。config.json有严格字段/类型/范围校验，未知字段和不合理组合直接报错，不自动忽略。

| 参数组 | 默认/含义 | 调整条件 |
| --- | --- | --- |
| model | models/milu.mud | 更换完整同版模型三件套 |
| uart_device/tx_pin/rx_pin/functions | UART4，A21/A22 | 换板或改接线同时改映射 |
| laser_pin/laser_active_high | A4/true | 依实际MOS信号和有效电平 |
| yaw_sign/pitch_sign | -1/+1 | 厂家参考安装，单轴实测反向才改 |
| yaw_limit/pitch_limit | 10/10 | 安装避碰验证后修改，上限90 |
| position_rpm | 30 | 厂家内部位置模式速度限制 |
| gain | 1.8 | 收敛慢可逐步增加，振荡先降低 |
| max_rate/max_accel | 12/60 | 先低速联调，结合负载增大 |
| hfov_deg/vfov_deg | 60/45 | 初调假设，替换镜头标定值 |
| smoothing_tau | 0.06 | 加大更平滑但更迟滞 |
| deadband | 0.02 | 按全图宽高归一化误差，降低可提高居中要求但更易抖动 |
| confidence/nms_iou | 0.65/0.45 | observe可试0.25提高召回，须观察误检 |
| association_radius/lock_timeout | 0.25/0.5 | 身份关联距离与重获超时，不是精确个体识别 |
| stale_after | 0.25 | 旧帧超过此值不驱动；先查实际推理延迟再调整 |
| loop_hz | 20 | 控制周期，非承诺相机帧率 |
| frame_gap/query_timeout/feedback_timeout | 0.002/0.08/0.5 | 含串行化间隔，每轴查询更早失败 |
| boot_wait | 1.5 | 上电等待 |
| aim_x/aim_y | 0.5/0.5 | 固定距离光轴标定值 |
| dwell/reached_tolerance | 0.5/0.3 | 连续稳定时间/反馈到位角误差 |
| laser_pulse/laser_cooldown | 0.15/2 | 最大光点许可窗口/冷却 |
| paper_roi | [0.1,0.1,0.9,0.9] | 目标中心允许的图像区域 |
| show_display | true | 显示检测框和校准十字 |

0.3新增 max_jerk=400、velocity_tau=0.15、max_lead=2、max_control_gap=0.2、deadband_hysteresis=0.008、settle_rate=0.25；单位及调参说明见 [平滑控制](smooth-control.md)。

建议顺序：接线和反馈→方向→限位→目标框质量→FOV和gain→速度/加速度→光轴和dwell。一次只改一组，记录相同距离与靶速下的日志。图像死区不等于毫米精度，0.1°协议量化也不能证明厂家宣传的0.05°系统精度。
