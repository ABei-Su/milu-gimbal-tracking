# 测温版0.3验证记录

2026-09-22，Windows CPython3.12，未连接MaixCAM2/F32C/D55实物。

- python tools/verify.py：130项离线测试通过，含格式、静态检查、语法与字节码；日志outputs/verify.log。
- 原版控制、温度状态机、UI失效与故障退出测试保留。
- 新增7项D55测试：配置/FOV、MaixPy构造参数/引脚映射、传感器检查有效数据、阻塞截止、错误/缺帧、ROI外坏值、重复帧。
- 官方示例ZIP下载成功，758条目CRC无错误，SHA256记录于thermal-hardware.md；仅阅读源码，不执行厂商脚本。
- 原版控制核心继续以base-version.json比对；部署包SHA256清单验证。
- python -m thermo.preflight在本PC仍报告无maix、无板端MixFormerV2模型和未标定；vendor_protocol与sensor_confirmed已通过。不能把PC能力预检失败误报为测试全失败或板端验收通过。

## 剩余实机验收

1. 记录板修订/MaixPy版本/镜头，确认官方MLX90640Celsius绑定存在。
2. 按四线表连接D55；执行python -m thermo.probe --frames 8 --timeout 15，核对物体升温时数据变化及读取时延。
3. 固定测量距离对齐RGB/IR，验证ROI方向与视场，再设置alignment_confirmed。
4. 用稳定参考热源验证发射率/温度偏移/像素覆盖，不以模拟35℃或手掌温度当精度标准。
5. 检查安装后负载、限位、线缆余量、运动方向；测试丢帧/断传感器/退出时的无效显示和执行器清理。
6. 测量20Hz循环最坏延迟、热像完整帧率、CPU/RSS和30分钟运行；据实测调整刷新和窗口。
7. 断电/主机硬崩溃下的物理保护依赖实际硬件，软件测试不替代此项。

旧0.1版的串口协议阻碍已由改用标准I2C模块解除；新驱动尚未在实物上验证，不能称为已烧录或精度达标。
