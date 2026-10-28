# 开发

Python 3.11+；PC开发先安装 requirements-dev.txt。单一完整代码检查命令：python tools/verify.py，包含Ruff格式/lint、语法编译、源文件卫生和全部unittest。未配置静态类型检查器；板端MaixPy SDK不由PC pip依赖替代。

训练依赖版本见requirements-training.txt与本机冻结requirements-training.lock.txt（CUDA12.8环境）。训练、数据审核和NPU转换属于离线模型流程，不让普通CI下载照片或模型。

原资料只读。公共行为更改补测试、CHANGELOG和必要ADR。主机测试不能代替板上抓包、故障注入及连续运行。Git分支开发，不自动push/merge。提交遵循Conventional Commits。
