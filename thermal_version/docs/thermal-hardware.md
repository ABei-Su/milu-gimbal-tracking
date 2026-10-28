# 微雪 MLX90640-D55 接入与资料

用户于2026-09-22明确停用旧GD32串口热像仪，并确认新模块为微雪D55。旧资料仅保留在ADR0004历史记录；当前接口为I2C，不再等待串口协议。

## 链接实际访问结果

- 用户淘宝短链：https://e.tb.cn/h.8Gm9dxB8iPIBR4Y?tk=sXt9TPGKI5J ，当前工具未能直接打开。
- 中文Wiki：https://www.waveshare.net/wiki/MLX90640-D55_Thermal_Camera ，直接访问返回网站验证页；不能声称正文完整打开。
- 官方同系列页面的搜索缓存提供下载地址；官方示例ZIP已成功下载并完成全部条目CRC检查。
- 官方ZIP：https://files.waveshare.net/wiki/w/upload/c/c9/Mlx90640_thermal_camera.zip
- 本地副本：vendor/waveshare/Mlx90640_thermal_camera.zip（开发目录中，不装到板端）。
- SHA256：0aaf3b9b21b7886c0e12e1446e36464d465d2547615b63fa93bac737e45f42be
- 共758个ZIP条目，包含Arduino、RaspberryPi、STM32示例；没有执行任何厂家脚本。

厂商源码核对：RaspberryPi/cpp/main.cpp使用MLX_I2C_ADDR=0x33，读取EEPROM校准参数，设置刷新率/棋盘模式，再读取帧和计算温度。板端使用MaixPy官方驱动，不把树莓派安装脚本或STM32固件烧到MaixCAM2。厂家原包留作查阅，保留原授权，不把它当新增生产依赖。

## 当前硬件契约

| 项目 | 当前约定 |
| --- | --- |
| 型号 | 微雪MLX90640-D55，用户已确认；硬件修订/芯片丝印实测TBD |
| 阵列/FOV | 32×24；55°×35°，D110的110°×75°不用于本配置 |
| 接口 | I2C，默认7位地址0x33；非UART、非USB视频 |
| 供电 | 厂商标称3.3V/5V；本项目选择3.3V供电 |
| 电流 | 厂商标称<23mA；实际板上供电余量需确认 |
| 温度 | 厂商目标温度-40～300℃；标称±2℃（室温0～50℃），未实测认证 |
| 刷新 | 厂商0.5～64Hz子页刷新（0.25～32FPS）；配置8Hz初调，不能当作已测8完整帧/秒 |
| 驱动 | MaixPy ext_dev.mlx90640.MLX90640Celsius，完整24行32列℃矩阵 |
| 配置 | thermal.json已设mlx90640_i2c、sensor_confirmed=true；表示型号接口已确认 |
| 标定 | alignment_confirmed=false，必须完成RGB/IR对齐才能显示有效眼周温度 |

## MaixCAM2新增四根线

按实际模块丝印对应，不凭线颜色或连接器照片顺序：

| 微雪D55端 | MaixCAM2端 |
| --- | --- |
| VCC | 3V3电源 |
| GND | GND |
| SDA | A0（I2C6_SDA） |
| SCL | A1（I2C6_SCL） |

选择3.3V供电与MaixCAM2逻辑电平一致。不要把VCC接12V电机电源；不要把SDA/SCL接UART TX/RX。原云台继续使用A21/A22 UART4，激光MOS继续A4，彼此不占同一数据引脚。新增模块无需烧录固件。实际扩展板接口位置以板上丝印为准。

依据：[MaixCAM2 I2C6引脚](https://wiki.sipeed.com/maixpy/doc/en/peripheral/i2c.html)、[MLX90640官方API](https://wiki.sipeed.com/maixpy/api/maix/ext_dev/mlx90640.html)及本次用户商品截图。接线后先运行传感器检查，再启动云台；I2C线尽量短，云台转动留足机械余量。

## 板端运行顺序

在MaixCAM2解压后的工程目录执行：

```sh
python -m thermo.preflight
python -m thermo.probe --frames 8 --timeout 15
python main.py
```

preflight只查SDK/模型/配置，不访问硬件。默认未标定会报告alignment=false；PC上没有maix和系统模型也会失败，这不是协议缺失。probe仅启动红外采集，输出8帧全场最小/最大与ROI P90/均值，发生SDK阻塞最长等待指定期限再清理进程，不打开相机/电机/激光。probe通过代表读到了有效形状/范围的温度数据，不证明精度或眼周对齐。

主程序初始TRACK OFF，触屏拖框后再开启跟踪。标定未完成时显示ALIGN_RGB_IR_FIRST；不能为消除提示而直接将alignment_confirmed改true。

## 光学与温度标定

thermal_gimbal.json的aim_x/aim_y、hfov_deg/vfov_deg用于RGB光轴/FOV；thermal.json的roi_cx/roi_cy指定红外ROI。用固定距离的稳定温热目标对齐中心，记录实际距离、两个镜头FOV、方向及偏差，再设alignment_confirmed=true。固定距离中心标定不等于全场配准，距离变化会有视差。

D55窄视场有利于扩大同一目标在红外阵列中的像素占比，但32×24仍不能保证远处眼周可分辨。厂家人体轮廓距离不等于眼周精确测温距离。ROI覆盖不足显示EYE_TOO_SMALL_FOR_IR_ROI。所有结果为表面温度，未做核心体温换算。

发射率默认0.95为实验初值，依据实际表面和参考温度验证；temperature_offset仅允许经参考仪器标定后的补偿。温度矩阵经范围/MAD/P90/多帧融合，不以彩色插值冒充真实空间分辨率。
