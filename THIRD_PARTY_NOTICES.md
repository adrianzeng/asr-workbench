# 第三方组件与许可声明

本文件随 ASR Workbench 安装包一起分发，说明包内每一个第三方组件的来源、许可证和再分发依据。
所有许可证全文放在同目录的 `THIRD_PARTY_LICENSES/` 下。

> 面向普通用户的一句话：这个包里除了我们自己的代码，还带了别人的程序和模型下载器；
> 下面写清楚它们是谁做的、按什么规矩可以用、出了事找谁。**你正常使用、转写自己的音视频，不受这些条款约束。**

---

## 一览表

| 组件 | 版本 | 在包里做什么 | 许可证 | 是否随包分发 |
|---|---|---|---|---|
| ASR Workbench（本项目） | V1.1 | 网页界面、后端、下载器 | MIT | 是（源码） |
| OneAsr | v1.4.1 | 本地听写与时间轴对齐 | MIT | 是（`oneasr-cli.exe`、`oneasr.exe`） |
| FFmpeg | 9.0.2 essentials build | 把音视频抽成 16 kHz WAV | GPL-3.0-or-later | 是（`bin/ffmpeg.exe`） |
| imageio-ffmpeg | 0.8.1 | 仅作为上面 FFmpeg 二进制的载体 | BSD-2-Clause | 仅二进制，未含其 Python 代码 |
| Python | 3.12.10 官方安装器 | 运行本项目后端 | PSF License | 是（用户手动双击安装） |
| Qwen3-ASR-0.6B / 1.7B | — | 听写模型权重 | 见各自模型卡 | **否**，首次启动自动从 ModelScope 下载 |
| omniASR-CTC-300M-v2 | — | 打时间轴模型权重 | 见模型卡 | **否**，同上 |

---

## 1. ASR Workbench（本项目）

MIT，版权归本项目贡献者，全文见仓库根目录 `LICENSE`。
本项目后端只用 Python 标准库，前端是原生 HTML / CSS / JS，**不引入任何第三方 Python 包、CDN、在线字体或外部图片**。

## 2. OneAsr —— MIT

- 上游：<https://github.com/eclipse005/OneAsr>，Release v1.4.1
- 版权：**Copyright (c) 2026 eclipse005**
- 许可证全文：`THIRD_PARTY_LICENSES/OneAsr-MIT.txt`（上游仓库 LICENSE 原文）

MIT 允许再分发二进制，条件是随附版权声明与许可全文 —— 本文件与上面的全文即为此目的。
包内 `runtime/oneasr/oneasr-cli.exe`、`runtime/oneasr/oneasr.exe` 均取自官方 Release，**原样分发、未做任何修改**。

**特别说明**：上游便携包原本自带一个 `bin/ffmpeg.exe`，其构建参数包含
`--enable-nonfree --enable-gpl --enable-version3`（已用 `ffmpeg -version` 核实）。
带 `--enable-nonfree` 的构建**不允许再分发**，因此本安装包**没有**收录那一份，
改成下面第 3 条所述的合规构建。上游的 `README.txt` 也随包保留。

## 3. FFmpeg —— GPL-3.0-or-later

- 版本：`ffmpeg version 9.0.2-essentials_build-www.gyan.dev`，Windows x86_64 静态构建
- 构建参数含 `--enable-gpl --enable-version3 --enable-static`，**不含 `--enable-nonfree`**
  （已用 `ffmpeg -version` 逐项核对）
- 来源：<https://www.gyan.dev/ffmpeg/builds/>（essentials build）
- 许可证全文：`THIRD_PARTY_LICENSES/GPL-3.0.txt`（GNU GPL v3 官方全文）
- 对应源码与构建信息的获取方式：
  - FFmpeg 源码 <https://ffmpeg.org/download.html> / <https://github.com/FFmpeg/FFmpeg>
  - 该二进制的构建配置与所用第三方库清单元数据，见 gyan.dev 构建页，以及随二进制 `ffmpeg -version` 输出的完整 configuration 行

本项目**只做原样再分发**，不修改、不静态链接、不把 FFmpeg 代码并入自身源码；
本项目自己的代码是 MIT，与 FFmpeg 仅通过命令行调用（进程边界）。
按 GPLv3 第 6 条，本文件连同 GPL 全文、上面的源码获取方式一并随包提供。

> 若你打算把本安装包用于商业分发，请在正式发布前再核一遍 gyan.dev 当期构建页的许可标注；
> 若改用其它来源的 FFmpeg，请同步替换这里的版本、来源与许可证说明。

## 4. imageio-ffmpeg —— BSD-2-Clause

- 上游：<https://github.com/imageio/imageio-ffmpeg>，wheel `imageio_ffmpeg-0.8.1`
- 版权：Copyright (c) 2019-2025, imageio
- 许可证全文：`THIRD_PARTY_LICENSES/imageio-ffmpeg-BSD-2-Clause.txt`

本项目**只提取了该 wheel 内附带的 `ffmpeg-win-x86_64-v9.0.2.exe` 这一个二进制**用于第 3 条，
**没有**打包或引用它的任何 Python 代码。按 BSD-2-Clause 第 2 条，其版权声明与免责条款随上面的全文一起附上。

## 5. Python 3.12.10 安装器 —— PSF License

- 来源：<https://www.python.org/downloads/release/python-31210/>，`python-3.12.10-amd64.exe`
- 许可证全文：`THIRD_PARTY_LICENSES/Python-PSFL.txt`（CPython 3.12 分支 LICENSE 原文）
- 由用户在自己电脑上运行官方安装向导完成安装，本项目**不修改安装器、不写系统 PATH 之外的东西、不写注册表项**。
- 提示：安装向导里勾选 `Add python.exe to PATH` 是 Python 官方选项，由用户自己决定。

## 6. 模型权重 —— 不随包分发

Qwen3-ASR-0.6B-hf、Qwen3-ASR-1.7B-hf、omniASR-CTC-300M-v2-hf 三个权重
**不在这个 zip 里**。首次启动时会由本项目的下载器从 **ModelScope**（国内源）逐文件下载，
每个文件带精确字节数与 sha256 校验，清单见 `models_manifest.json`。

- Qwen3-ASR：<https://www.modelscope.cn/models/Qwen/Qwen3-ASR-0.6B> 及 1.7B 对应模型卡
- omniASR-CTC：<https://www.modelscope.cn/models/omniASR/omniASR-CTC-300M-v2>（以实际仓库为准）

权重的使用、再分发与商用条件**以各模型卡当前标注的许可证为准**，请在使用前自行查看。
本项目不托管、不镜像、不修改这些权重，只提供下载与校验工具。

## 7. 权利人联系与下架

若你是上述任一组件的权利人，认为本安装包的分发方式不妥，
请通过网页「关于作者」里的微信二维码联系本项目作者，说明组件名与理由，
核实后会在下一个版本中移除或改用合规来源。

---

## 发布前核对清单（给维护者）

1. `ffmpeg -version` 输出里**不得**出现 `--enable-nonfree`。
2. OneAsr MIT 版权行与 `OneAsr-MIT.txt` 一致；上游 Release 若换版本，重新核对。
3. `bin/ffmpeg.exe` 的版本、来源、许可证三项与本文一致。
4. Python 安装器版本号与 `Python-PSFL.txt` 对应分支一致。
5. 模型权重**不得**被打进 zip；`runtime/oneasr/models/` 里只应有 `.keep`。
6. 若新增任何第三方组件，先补本文件与 `THIRD_PARTY_LICENSES/` 再打包。
