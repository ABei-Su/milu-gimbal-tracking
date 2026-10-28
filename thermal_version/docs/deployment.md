# 烧录、接线和第一次运行

## 烧录在哪里

**应用代码与模型放在 MaixCAM2 的 Linux 文件系统。F32C 电机继续使用 WHEELTEC 原厂程序。** 这套方案直接用 MaixCAM2 串口控制 F32C，无需 C30D/STM32F4 控制板。厂家 STM32 绘图例程用于核对协议、方向和时序。

MaixCAM2 有 eMMC 和无 eMMC/SD 启动版本。已有正常 MaixPy 系统时只上传应用，不必刷整机。若必须恢复系统，按 [官方 MaixCAM2 刷机说明](https://wiki.sipeed.com/hardware/zh/maixcam/maixcam2_os.html) 选择与实物版本匹配的系统镜像及烧录工具：普通 .img 与 _sd.img 不混用。系统刷机会影响板上原有文件，先备份。当前未连接开发板，未执行实际烧录。

## 接线表

先断电接线。线序按连接器定义核对，不能仅凭线色判断。

| MaixCAM2 / 电源 | 连接对象 | 说明 |
| --- | --- | --- |
| A21 / UART4_TX | F32C RX | 3.3 V TTL |
| A22 / UART4_RX | F32C TX | 反馈必须连接 |
| GND | F32C、MOS 控制地 | 分路供电仍须共地 |
| A4 / GPIOA4（本项目选定，可改） | MOS 信号端 | 默认高电平有效，须与实际 MOS 一致 |
| 独立合规 Type-C 电源 | MaixCAM2 | 不从电机信号接口给板供电 |
| 12 V 电池 | F32C 电源端 | 厂家允许8–15 V，核对满电电压 |
| 电池→DCP3512低压支路 | MOS/650 nm光源 | 按模块额定3.3–5 V设置并实测 |

UART4 映射采用 [官方 UART 示例](https://wiki.sipeed.com/maixpy/doc/en/peripheral/uart.html)。A4 是本项目的可修改选择，不是厂家接线事实。GPIO仅控制MOS，不直接给激光或电机供电。实际MOS型号、有效电平与上电默认关断电路仍需核对；低功率光源用于封闭纸靶区域。详见 [GPIO官方说明](https://wiki.sipeed.com/maixpy/doc/en/peripheral/gpio.html)。

厂家要求禁止热插拔。滑环电流和部分电源端标注在随附资料中存在差异，未将其作为视觉板电源路径，见硬件契约。

## 上传

1. PC 解压 `dist/milu_maixcam2.zip`。
2. 用 MaixVision 连接 MaixCAM2，通过文件管理上传完整目录，例如板端 `/root/milu`。必须包含 `main.py`、`config.json`、`milu/`、`models/milu.mud` 及两个 axmodel。只点击“运行”单个 main.py 不会自动传齐依赖。
3. 在板端终端中进入目录。使用 MaixPy 系统自带 Python3，不要在板上安装 PC 的 torch/ultralytics。
4. 运行下列命令。MaixVision 无命令行参数启动时，默认取 main.py 中 RUN_MODE；首次保持 observe。项目附 app.yaml，可按 [官方应用打包流程](https://wiki.sipeed.com/maixpy/doc/en/basic/app.html) 用 maixtool release 生成启动器安装包。dist ZIP 是完整文件包，不冒充启动器安装格式。

```sh
cd /root/milu
python3 -m milu.diagnose
python3 main.py --mode observe --seconds 30
```

诊断检查板型、模型和引脚映射，不打开UART/GPIO。观察模式显示框与瞄准十字，不控制电机或光源。使用真实麋鹿照片打印靶测试，卡通轮廓不保证能识别。

## 单轴和跟踪

固定云台、保持初始姿态在可动区中间。程序把启动后反馈位置作为本次软件零点，不写入电机Flash，不等于恢复厂家机械零点。

```sh
python3 -m milu.diagnose --jog-axis yaw --delta 1
python3 -m milu.diagnose --jog-axis pitch --delta 1
python3 main.py --mode track --seconds 30
```

每次单轴检查最多±2°、3秒，光源保持关闭。默认安装对应 yaw_sign=-1、pitch_sign=+1；右侧目标应使其向画面中心靠近。反向时先停机，只修改对应 sign 后重试。相机必须固定在随云台转动的支架上，并与坐标方向一致。

track 只跟踪，光源关闭。首次±10°、最大12°/s、加速度60°/s²；确认避碰后才提高限位，配置不允许超过厂商软件±90°。型号资料不能代替实际支架/线缆可动范围。

## 纸靶光点

在固定实验距离，以低功率光点落点测得相机画面坐标（x,y）。相机/光源不共轴时需要把瞄准十字改为该落点；PC 上生成新配置：

```powershell
.venv/Scripts/python.exe tools/calibrate_aim.py --width 640 --height 480 --spot-x 320 --spot-y 240
```

上例仅表示画面中心，替换成实测数值。输出 config.calibrated.json，原文件保留。上传后：

```sh
python3 main.py --config config.calibrated.json --mode paper --seconds 30
```

paper 要求唯一目标、帧龄≤0.25秒、目标居中、实测角度接近上一目标、未触限，并在ROI内稳定0.5秒，才允许0.15秒光点窗口；窗口内每轮I/O前短暂关断，2秒冷却。多目标、丢失、超时、异常立即撤销许可。ROI是图像中心区域，不是物理防护围栏。距离改变会产生视差，应重新校准。Word不要求光点参与检测，本版也不从光点反推命中评分。

Ctrl+C 或到达 --seconds 后退出。软件清理无法覆盖系统死机、强杀和断电；硬件MOS应具有默认关断，电机应有可直接切断的电源。失能后俯仰负载可能下垂，安装时提供支撑。

## 常见现象

| 现象 | 查看/处理 |
| --- | --- |
| Missing model | mud 和两份 axmodel 必须同目录 |
| pinmap failed | 按实物引脚与SDK检查 config；未正确映射即停止 |
| NO_FEEDBACK | 先查交叉TX/RX、共地、115200、ID1/2；禁止忽略反馈继续运动 |
| 越跟越偏 | 单轴检查安装方向和 sign |
| 抖动 | 先降低 gain/max_rate，检查目标框质量与支架松动 |
| 识别有框但不点灯 | 查帧龄、多个框、居中、反馈到位、ROI、dwell |
| 目标漏检 | observe 中可试 confidence=0.25；默认0.65偏保守，需现场对比误检 |
| 进程报错退出 | 查看 logs/runtime.log；修复原因后重新启动 |

日志最多约3 MB。板端首次记录系统/SDK/电机固件版本、实际帧率、CPU内存和温升，填写 validation.md 中的验收项。
