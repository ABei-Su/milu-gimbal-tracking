# v1.0.0 封板（2026-10-13）
用户确认当前yaw-gentle-v2跟随效果良好并指定为v1.0。冻结现有算法与config.json，本次仅更新版本标识和封板文档。后续调参需另立版本，不覆盖本次归档。
- MaixCAM2人脸跟随；UART2 B0 TX、B1 RX、GND，115200 8N1；电机1左右，电机2上下。
- 左右增益1.12、参考领先6.5度，左右软件角度限位关闭；上下±90度。
- 共用速度上限42度/秒、加速度180度/秒²、加加速度2400度/秒³；控制目标50Hz。上下算法与前版一致。
- 启动相对抬头最多60度，发现有效人脸提前结束搜索；不是绝对水平回零。
- 使用板载兼容AX人脸模型，部署包不包含权重；激光始终禁用。
验收依据：用户实机反馈及主机离线验证。并非工业可靠性或长时间负载验收；实际延迟、线材连续绕转余量、负载温升未全面验证。原麋鹿版和测温版不变。
MaixVision打开完整项目并运行项目，启动显示[BUILD] v1.0.0 | yaw-gentle-v2 frozen。

当前部署yaw-gentle-v2-20261013：左右领先6→6.5度、增益1.08→1.12，沿用已获用户好评版本的小幅调参方式。速度/加速度/加加速度、上下参数、搜索60度及丢目标规则均不变，左右角度限位仍关闭。最新106条日志中有效目标最大左右差值5.308度；丢脸保持误差不用于放宽运动参数。实机卡顿/延迟改善待复测，可能增加超调。回退设yaw_max_lead=6、yaw_gain_multiplier=1.08，见ADR0020。

当前左右温和调优（yaw-gentle-20261013）：yaw_max_lead=6度，yaw_gain_multiplier=1.08；其余平滑参数、上下控制、启动60度及人脸提前结束保持。左右角度限位仍关闭。日志lead_deg为目标减实际角度，不是限位事件计数。更大领先可能增加超调，实机平滑/延迟改善待验证。恢复yaw_max_lead=0、yaw_gain_multiplier=1即回到本次调优前响应。完整离线检查137项通过，见ADR0019。

当前部署：用户要求取消左右软件角度限位，yaw_limit_enabled=false；不在±90/180/360度停转。不改变当前平滑控制参数，上下±90度、启动搜索60度及提前识别停止保持。旧配置默认仍启用限位；设置true可恢复yaw_limit。输入有限数、通信超时和F32C累计角度协议范围检查保留；不允许无限数指令。连续绕转可能缠绕外接线。主机135项测试通过，实机待验收。详见ADR0018。

截图版本核对：当前控制参数与ADR0014的两轴统一平滑版本一致；启动新增标记 `[BUILD] 0.3.1-restored-20261013`，用于核对是否运行本次部署入口。标记不改变控制行为，也不能单独证明所有模块均已同步，需运行完整项目。旧包没有留存，仍为按修改记录恢复。

# 当前部署：按用户要求回退至0.3.1控制行为
撤销0.3.2请求速度滤波层及0.3.3范围修改；恢复两轴共用42/180/2400运动参数、70ms速度响应、25ms图像滤波、30ms预测、5度领先。保留逐轴反馈恢复。启动最大抬头60度，识别人脸提前结束；跟随双轴限位±90度。到旧限位仍会停止该方向运动。
仓库没有历史提交，此回退依据ADR0014及逐项修改记录恢复行为，不声称与旧包逐字节一致。回退前源码和后续版本专用测试保存至D:/milu/tmp/person_follow_before_031_rollback。后面的0.3.2/0.3.3说明仅为历史记录。
本次FEEDBACK_OUTSIDE_LIMIT原因未证实，未放宽或移除反馈检查。回退后机械表现仍待实测。

# 0.3.3 左右旧限位修复
实机日志显示左右目标持续卡在-90度，上下仍运动。左右跟随范围扩大为相对本次跟随起点±180度（总360度），上下仍±90度，不支持无限绕圈。方向和厂家电机参数不变。
撤回0.3.2额外40ms请求滤波（request_tau=0），保留两轴相同的连续加减速控制；开局最多抬头90度、发现有效脸提前结束不变。
日志新增angle_limit_axes：()表示未到角度边界，('yaw',)表示左右到边界，('pitch',)表示上下到边界。修复反馈89.9而目标90时漏报限位。到边界仍可反向离开。
软件回归通过不等于机械丝滑已验收。实际卡顿还需本版板端复测；原麋鹿版与测温版不改。MaixVision运行整个person_follow_test项目，需同步config.json和milu目录。详见ADR0016。

# 0.3.2 当前部署：速度请求平滑与90度搜寻
两轴速度请求增加40ms平滑，减轻约17FPS检测输入带来的分段变化；保留50Hz控制与连续加减速。不进一步降低速度上限，可能增加少量跟随相位滞后。request_tau=0可关闭新平滑用于对比。
开局最大相对抬头改为90度，仍6度/秒（无目标时运动约15秒）。途中检测到有效人脸立即结束继续抬升并转跟随。重复启动仍会重新执行相对搜寻，不能当作绝对水平回零。
仅软件/主机验证，实际机械卡顿是否改善仍需板端测试；原麋鹿版、电机厂家PID不改。

# 0.3.1 当前部署：两轴统一平滑控制
修复一个轴反馈超出参考领先范围时把两轴速度同时清零的问题：仅对异常轴重建参考，另一轴继续原有连续运动。目标丢失/切换/控制超时仍按原规则处理。
左右和上下统一增益倍率及运动参数，撤销左右激进覆盖。共用速度上限42度/秒、加速度180、加加速度2400、响应时间70ms、图像滤波25ms、预测30ms、领先5度。适度降低极速和起步强度换取平滑；不声称消除了实机抖动。
保留边抬头边检测，检测到有效脸立即结束启动抬升；最大搜寻60度。原麋鹿版和电机厂家PID未修改。

# 0.3.0 当前部署：边识别边抬头搜寻，独立左右追赶
启动先等待相机产生新鲜画面，再开始最多60度的相对抬头搜寻（6度/秒）。启动已有人脸则不抬；途中检测到新鲜且达到confidence的人脸，停止继续抬升并以实际位置转入跟随，日志出现[SEARCH] FACE_ACQUIRED。未找到则到60度保持等待，不自动反复扫动。此位置不是绝对水平零位。
左右轴独立速度上限60度/秒、加速度360度/秒²、加加速度5000度/秒³、参考领先8度。上下跟随参数保持原值。实际速度仍由反馈与连续轨迹约束决定；不能保证快速运动永不出框。
search_during_lift=false可恢复固定抬头；yaw_max_rate/yaw_max_accel/yaw_max_jerk/yaw_max_lead设为0恢复共用参数。模型/电气协议不变，原麋鹿版不改。
参考：ViSP图像视觉伺服 https://github.com/lagadic/visp ，Ruckig连续轨迹与逐轴约束 https://github.com/pantor/ruckig 。未复制代码、未引入这些依赖，也不声称实现其完整算法。

# 0.2.8 当前部署：启动抬头60度
仅将相对启动抬头45度改为60度，保持6度/秒（运动约10秒）。到位后开启人脸检测。上下跟随参数、左右既有调优保持不变；后续算法调优优先底部1号左右轴，不自动修改原麋鹿版本。
每次运行都会相对再抬60度，应从预期下垂姿态开始；该动作不代表水平归零。

# 0.2.7 当前部署：先抬头45度，再检测人脸
启动保持1号位置，2号向上相对抬45度，参考速度6度/秒，运动约8秒，到位后启动人脸识别。未检测到脸保持当前位置，不自动扫动。每次运行都会再次相对抬45度，不保证绝对水平；从预期的下垂姿态开始测试。
根据84条实机日志，保留已调顺的上下/左右轨迹参数。改为先查询电机反馈、再读取最新视觉结果，避免读取画面后再等一次UART查询。保留50Hz控制及现有预测，主机验证不能证明实机延迟降低幅度。
以下版本记录为历史行为，以本段当前部署说明为准。

# 0.2.6 左右独立响应
左右视觉误差增益提高30%（yaw_gain_multiplier=1.3），上下参数完全保留。速率/加速度/加加速度仍沿用0.2.5；这不是物理延迟降低30%，饱和时仍受轨迹限速。快速换向超调待实测；将该倍率改回1即可恢复上一版左右响应。

# 0.2.5 更快跟随与小幅延迟补偿
控制目标50Hz，参考速度上限42度/秒、加速度240、加加速度4000；图像滤波15ms。新增最多60ms、最多画幅2.5%的图像运动预测，目标丢失/切换清除预测，中心死区不预测。真实检测和物理延迟未消失，快速反向可能超调，待实机验证；prediction_horizon设为0可关闭预测。启动仍相对上抬10度，方向不变。

# 0.2.4
- 调整部署跟随响应：20→40Hz、速率上限12→36度/秒，放宽参考领先并缩短滤波，保留连续加减速。
- 增加控制频率、识别帧率/耗时、反馈查询耗时日志。
- 增加17Hz视觉输入下响应、平滑性与堵转参考限制回归。

# 0.2.3
- 按用户确认方向改为启动相对抬头10度，1号保持；不再追机械零位。
- 保持正确的人脸上下跟随符号，增加启动抬头边界与方向回归测试。

# 0.2.2
- 回零偏差报错输出电机编号、参考/实测角、误差及最终目标，保留3度保护。
- 补充机械零点保存与掉电复查步骤；不擅自反转回零方向。

# 0.2.1
- 修复100度启动回零保护阻止大角度回正：允许最短180度，超时45秒。
- 回零提前到视觉启动之前，取消启动主动失能；跟随范围双轴±90度。
- 回零日志输出双轴机械角/累计角，越界错误包含轴与角度。

# Changelog

## 0.2.0 - 2026-10-12
- Add bounded, cancelable mechanical-zero homing using kind-2 feedback; never send cumulative angle zero as a substitute for mechanical zero.
- Lock missing-target hold once instead of following sag every tick; rebase on reacquisition.
- Add actual face detection backend with strict MaixCAM2 AX weight validation and auto discovery. No person-box proxy. Compatible board face weights and hardware behavior still require verification; no model training claimed.
- User confirmed mechanical zero calibration and clearance: deployed limits yaw +/-35, pitch +/-25 degrees; home rate 6 deg/s, maximum initial travel 100 degrees, timeout 30s.
- Model validation happens before actuation. Missing face model reports FACE_MODEL_REQUIRED and inventory; the application will not move in this case.

## 0.1.3 calibration
- User hardware calibration: yaw_sign changes from -1 to +1 after confirmed reversed horizontal following. Pitch remains +1, not yet calibrated. UART2 returned six valid position replies; user selected track. Horizontal correction awaits board retest.

## 0.1.3 - 2026-10-12
- Select UART2 B0/B1 /dev/ttyS2 in defaults and deployment config at user request.
- Keep diagnose default; motor feedback on new pins remains unverified.
- Add config/default pin-selection regression and update wiring documentation.

## 0.1.2 - 2026-10-12
- Add bounded query-only diagnose mode for IDs 1/2, raw RX evidence and three attempts per ID.
- Temporarily default to diagnose for unresolved hardware communication; 97 offline tests pass.

## 0.1.1 - 2026-10-12
- Fix UART4 competing readers: remove the Maix default listener in parent and vision processes before actuator startup.
- Add four listener-release regressions; full offline suite: 94 passing. Board feedback recovery awaits retest.

## 0.1.0 — 2026-10-12
- 独立人体跟随测试应用，使用官方 COCO YOLO11 person 类。
- 保留原有 F32C 平滑控制，默认跟随模式，提供观察模式。
- 禁用纸靶模式和激光开启，补充模型、退出与部署说明。
