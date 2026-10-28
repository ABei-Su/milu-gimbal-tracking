# 数据、训练及MaixCAM2模型

2026-09-21实际下载 [iNaturalist麋鹿 Elaphurus davidianus](https://www.inaturalist.org/taxa/42230-Elaphurus-davidianus) 的140张照片，保存来源、作者署名、许可、观测ID、SHA256。manifest在data/milu_inaturalist/manifest.jsonl。包含CC BY-NC及BY-NC-SA，当前数据和派生试验产物按非商业研究使用，重分发需逐项保留归属并审核各许可；本项目不授予第三方照片/模型的新许可。Ultralytics代码/权重许可另行遵守其AGPL或商业条款。

YOLO-World deer提示生成候选框；92张有候选框进入数据集，56训练/19验证/17开发测试，按摄影者分组，固定seed42。同一摄影者不跨集合。48张无候选框被排除，未当作可信负样本。review目录含可视化标注。候选框存在漏框和边界偏差；物种名称来自观测元数据，未经逐张人工鉴定。普通鹿或其他动物负样本不足，所以不能声称已证明“麋鹿与所有鹿种区分”的能力。

训练YOLO11n，冻结前10层、AdamW lr0=0.0005、100 epochs、640输入、batch8、seed42、CUDA RTX4060。权重models/milu_prototype.pt；训练记录runs/milu_finetuned。独立留出的开发测试对机器候选框：mAP50=0.8677，mAP50-95=0.5842。**这是对伪标签的一致性，不是真实识别准确率。**

阈值在验证集0.25/0.40/0.55/0.65比较，最高F1为0.25；其开发测试TP23/FP5/FN9，P=0.8214、R=0.7188。报告models/threshold_report.json。默认板端0.65更保守，可能漏检，可在observe对照调整。评估采用PC浮点模型/图像缩放，与板端640×480直读及INT8模型有差异。

## 重现

先在PC安装与GPU匹配的PyTorch，再装requirements-training.txt。实际本机环境锁于requirements-training.lock.txt；不在MaixCAM2安装训练依赖。

```powershell
.venv/Scripts/python.exe tools/fetch_milu.py --allow-noncommercial
.venv/Scripts/python.exe tools/train_milu.py --prepare
.venv/Scripts/python.exe tools/check_dataset.py
.venv/Scripts/python.exe tools/train_milu.py --train --epochs 100
.venv/Scripts/python.exe tools/evaluate_detector.py
.venv/Scripts/python.exe tools/prepare_conversion.py
.venv/Scripts/python.exe tools/check_conversion.py
docker run --rm --entrypoint /bin/sh -v D:/milu/outputs/maixcam2_convert:/data -w /data pulsar2:6.0-lite convert.sh
```

请以各脚本--help中的参数为准。下载内容随iNaturalist变化，复现既有训练应保留manifest和当前照片，不重新下载覆盖版本。准备脚本会更新生成的数据集和划分，原始照片保留；人工修订前另存标注版本。

Pulsar2采用官方6.0-lite、目标AX620E（MaixCAM2转换目标名），分别NPU2与NPU1，校准只用56张训练照片。原始ONNX输入1×3×480×640；Ultralytics8.4的原始Concat节点与旧示例含义不同，脚本从三个尺度的box/class卷积输出重建65通道检测头，再输出NHWC，DFL/NMS留给MaixPy。数值回解与原ONNX比较由check_conversion验证；不能机械抄节点名。

输出outputs/maixcam2_convert/out中的milu.mud、milu_npu.axmodel、milu_vnpu.axmodel复制到models/，再运行tools/package_app.py。板端读取mud，不读取pt/onnx。

参考：[官方训练](https://wiki.sipeed.com/maixpy/doc/en/vision/customize_model_yolo.html)、[官方转换](https://wiki.sipeed.com/maixpy/doc/en/ai_model_converter/maixcam2.html)、[Pulsar2发布](https://huggingface.co/AXERA-TECH/Pulsar2/tree/main/6.0)。

下一轮实物改进需要记录实际打印靶/摄像头图像，人工补齐框和同场景负样本，按拍摄会话划分集合，重训并测板端漏检/误检和速度。当前已经提供可运行原型权重，但这项现场验收不能由厂家电机手册替代。
