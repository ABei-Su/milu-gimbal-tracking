# 麋鹿全身检测模型 · YOLO11n

基于用户人工标注照片训练的单类别目标检测模型，类别 `0: milu`（麋鹿全身）。用于 PC 视觉实验及后续 MaixCAM2 模型转换。

## 文件
- `weights/best.pt`：已完成训练并评估的 PyTorch 最佳权重。
- `weights/best.onnx`：固定 RGB NCHW 输入 `[1,3,480,640]`、opset 17 的 ONNX 导出，输入归一化至 0–1；输出为解码后的检测结果，尚需置信度筛选和 NMS。
- `training/`：训练脚本、训练参数、数据配置示例。
- `evaluation/`：训练曲线原始指标及测试集评估结果。
- `SHA256.json`：文件完整性校验。

## 已完成训练与测试
初始预训练模型：`yolo11n.pt`；640 输入；AdamW；学习率 0.001；batch 8；seed 42；CUDA；AMP 关闭。
最多 100 轮，在第 78 轮早停，验证集最佳为第 58 轮。

| 测试集指标 | 数值 |
| --- | ---: |
| Precision | 84.08% |
| Recall | 77.74% |
| mAP@0.5 | 86.29% |
| mAP@0.5:0.95 | 43.51% |

以上来自 110 张留出测试图。Precision/Recall 使用验证器选定的运行点，不代表任意固定置信度阈值的结果。
后续低学习率微调中途停止，未完成最终评估，因此本仓库发布已完成评估的原最佳模型。

## 数据与限制
原始 738 张图、728 份 XML；10 张缺少 XML 的图片排除；1874 个标注框。
508 张训练、110 张验证、110 张测试。精确哈希及 dHash 距离不超过 4 的连通组统一划分，seed 42，共 713 组。
同拍摄会话可能跨组，不能保证完全独立；可能存在远处或遮挡动物漏标。
普通鹿、其他动物和空场景等负样本不足，不能依据这些结果声称已具备可靠物种鉴别或野外泛化能力。
原始图片和标注未包含在公开仓库。

## PC 使用
Python 3.12 环境。训练使用 PyTorch 2.7.1+cu128；CUDA 版本需与本机环境相适配。
```bash
pip install -r requirements.txt
yolo predict model=weights/best.pt source=your_image.jpg conf=0.5
```

Python 示例：
```python
from ultralytics import YOLO
model = YOLO("weights/best.pt")
results = model.predict("your_image.jpg", conf=0.5)
```

如需使用自行准备且获授权的数据重新训练，将图片及 YOLO 标签放到 `dataset/`，按 `training/data.example.yaml` 配置 `dataset/data.yaml`，从仓库根目录执行：
```bash
python training/train.py
```
训练脚本会生成 `run/`，完成后评估测试集并导出 ONNX；已存在 `run/` 时拒绝覆盖。数据集未公开，运行需自行提供数据。环境和随机种子并不保证跨硬件逐位复现。

## MaixCAM2 状态
**这份 PT/ONNX 不能直接放进 MaixCAM2 当作 `.axmodel` 运行。**
还需要 AX620E 量化编译、输出头适配及板端验证；本仓库尚未提供本次训练的 `.axmodel`。
云台、电机控制及人脸跟随 v1.0 程序不属于此模型仓库。

## 许可
见 [NOTICE.md](NOTICE.md) 和 [LICENSE](LICENSE)。基于 [Ultralytics YOLO](https://github.com/ultralytics/ultralytics)。
