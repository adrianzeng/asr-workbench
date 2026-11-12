# ASR Workbench

一个独立、离线、零耦合的本地语音转写工作台。

把音视频文件放进 `inbox/`，在网页里点一下，得到带时间轴的 SRT 字幕和通顺的 TXT 文稿。
转写全程在本机完成，不上传任何音频，不需要账号，不依赖任何笔记软件、知识库或内部系统。

---

## 1. 这个项目的边界

- **独立**：自带前端与极薄后端，不依赖任何外部业务系统。
- **零耦合**：不读写你的笔记库、灵感库、Obsidian 仓库或任何其它目录；所有路径都在设置页里配置，默认只碰项目自己的 `inbox/`、`work/`、`output/`。
- **零第三方 Python 依赖**：后端只用 Python 标准库。
- **离线**：模型下载完成后，转写过程可完全断网。**当前版本不发起任何外部网络请求。**

目前只包含「听写 + 打时间轴 + 导出」。语音助手（实时麦克风与朗读）不在此版本；「改稿引擎」只预留了 OpenAI 兼容接口（见 5.1），**默认关闭、不生效、不联网**。

---

## 2. 环境要求（先配好，再启动）

| 组件 | 版本 | 用途 |
|---|---|---|
| Python | **3.12 或更高** | 运行本地后端（仅标准库） |
| ffmpeg | 任意较新版本 | 把音视频抽成 16 kHz 单声道 PCM WAV |
| OneAsr | v1.4.1 或更高 | 本地 ASR 与 CTC 对齐，出 SRT / TXT |
| ASR 权重 | Qwen3-ASR-0.6B-hf | 听写模型（约 1.5 GB） |
| 对齐权重 | omniASR-CTC-300M-v2 | 打时间轴（约 1.3 GB） |

> 后端不调用任何云端 API。以上组件全部在本机。

---

## 3. 环境配置指导

### 3.1 Python（Windows）

1. 到 <https://www.python.org/downloads/windows/> 下载 **Python 3.12 的 Windows installer (64-bit)**。
2. 运行安装程序，**务必勾选 `Add python.exe to PATH`**（这一步决定后面所有命令能不能直接调用）。
3. 可选：装到所有用户（`Install for all users`），需要管理员权限；不勾则只对当前账户可见，本项目同样可用。
4. 打开**新的**终端（旧终端不会读到新的 PATH），验证：

```powershell
python --version
python -m pip --version
py -0p        # 可选：仅当安装了官方多版本启动器时才有
```

**如果输入 `python` 弹出微软商店**：这是 Windows 的「应用执行别名」抢走了命令。
到 `设置 → 应用 → 高级应用设置 → 应用执行别名`，把 `App Installer - python.exe` 和 `python3.exe` 两个开关关掉；
或者确保真 Python 的目录排在 PATH 最前面。用 `where python` 检查第一条路径是不是你刚装的那个。

### 3.2 Python（macOS / Linux）

系统自带 Python 版本通常偏旧或不带 venv，建议用包管理器装 3.12：

```bash
# macOS
brew install python@3.12

# Ubuntu / Debian
sudo apt install python3.12 python3.12-venv
```

验证 `python3 --version`。本项目后端用 `python3` 或 `python` 启动均可。

### 3.3 ffmpeg

Windows 用户可从 <https://www.gyan.dev/ffmpeg/builds/> 下载 essentials build，
解压后把 `bin/ffmpeg.exe` 所在目录加进 PATH；macOS 用 `brew install ffmpeg`，Linux 用 `apt install ffmpeg`。

验证：

```bash
ffmpeg -version
```

如果不想改 PATH，也可以把 ffmpeg 的完整路径直接填进设置页的 `ffmpeg` 一栏。

### 3.4 OneAsr 与模型

1. 从 <https://github.com/eclipse005/OneAsr/releases> 下载对应平台的便携包并解压。
2. 便携包自带 ffmpeg，但不含模型权重。用 GUI 的「设置 → 下载模型」，或命令行：

```bash
oneasr-cli download --model 0.6b
oneasr-cli status --json
```

3. `status` 里 `can_start.ok` 为 `true` 即环境就绪。模型默认落在便携包的 `models/` 下；
   如果你用 `--data-root` 指定了别处，把同一个路径填进本项目设置页的 `oneasr_data_root`。

> 模型较大（合计约 2.8 GB），首次下载需要联网；之后可离线使用。
> 中国大陆用户模型走 ModelScope 源，速度通常明显快于 GitHub。

### 3.5 一次性自检

```bash
python --version
ffmpeg -version
oneasr-cli status --json
```

三条都通过，就可以启动了。

---

## 4. 安装本项目

```bash
git clone <your-repo-url>
cd ASR_Workbench
cp config.example.json config.json      # Windows PowerShell: Copy-Item config.example.json config.json
python server.py
```

浏览器打开 <http://127.0.0.1:8765>（端口可在 `config.json` 改）。
服务只监听 `127.0.0.1`，不对外网开放。

`config.json` 已被 `.gitignore` 忽略，里面可以放心写你本机的绝对路径。

---

## 5. 配置说明

| 字段 | 说明 | 默认 |
|---|---|---|
| `ffmpeg` | ffmpeg 可执行文件名或完整路径 | `ffmpeg` |
| `oneasr_cli` | `oneasr-cli.exe` / `oneasr-cli` 的完整路径 | 空（必填） |
| `oneasr_data_root` | 传给 OneAsr `--data-root` 的路径；留空则用 OneAsr 默认 | 空 |
| `inbox_dir` | 放待转写音视频的目录 | `./inbox` |
| `output_dir` | SRT / TXT 产物目录 | `./output` |
| `work_dir` | 中间 WAV 目录 | `./work` |
| `language` | 识别语言，如 `zh` / `yue` / `en` | `zh` |
| `asr_model` | `0.6b` 或 `1.7b` | `0.6b` |
| `aligner` | `ctc` 或 `qwen` | `ctc` |
| `backend` | `auto` / `cpu` / `gpu`。没有独显的普通笔记本选 `cpu`，0.6B 模型照样能跑，只是慢一些 | `auto` |
| `rewrite_engine` | `off`（默认）/ `openai`。**接口预留，当前不生效** | `off` |
| `rewrite_base_url` | OpenAI 兼容服务的 `/v1` 地址（云端，或本机 Ollama / LM Studio） | 空 |
| `rewrite_api_key` | API Key；只存本机 `config.json`，返回浏览器时脱敏 | 空 |
| `rewrite_model` | 模型名，如 `qwen3-vl-8b`、`deepseek-chat` | 空 |
| `port` | 本地服务端口 | `8765` |

所有目录都可以填绝对路径；留相对路径时以项目根目录为基准。

### 5.1 改稿引擎（接口预留）

这是一个**只留接口、不接线**的功能位：配置字段、界面表单、后端扩展点（`rewrite.py`）和 API 都已就位，但**本版本不会发起任何网络请求**，也不会改动转写出来的文稿。默认 `off`。

| 现状 | 说明 |
|---|---|
| 能做的 | 保存 Base URL / API Key / 模型名；界面显示当前状态；`GET /api/rewrite` 查状态、`POST /api/rewrite` 拿到原样返回的文本与明确状态 |
| 不做的 | 不请求 `/chat/completions`、不装任何 SDK、不引入额外依赖、不上传任何内容 |

将来要启用，只需实现 `rewrite.py` 里的 `rewrite_draft()`（文件内已附标准库 `urllib.request` 的调用示例），配置、界面、接口都不用改。同一个 OpenAI 兼容口子既能接云端（DeepSeek / 通义 / OpenAI），也能接本机 Ollama / LM Studio 里跑的模型。

**隐私约定（将来启用时必须遵守）**：只发送**文字稿**、绝不上传音频；界面要显式提示文本将发给哪个服务；默认必须保持关闭。

---

## 6. 使用

1. 把音视频文件放进 `inbox/`（或在设置页把 `inbox_dir` 指向别的目录）。
2. 网页「① 进件」里刷新，选中文件，点「开始转写」。
3. 「② 草稿 ↔ 成稿」并排显示带时间轴的 SRT 与纯文稿 TXT。
4. 「③ 出口」显示产物路径，可直接打开 `output/` 取用。

支持常见音视频格式：wav / mp3 / m4a / flac / aac / ogg / mp4 / mkv / mov / webm / avi 等。

**命令行单次转写（可选）**：不想开网页，或所在终端限制了后台服务派生子进程时，可直接跑一次：

```bash
python server.py --once demo.mp4
```

参数是 `inbox_dir` 里的文件名，产物同样落到 `output_dir`。这条路径不需要常驻服务。

---

## 7. 为什么后端要先转一道 WAV

OneAsr 在部分 Windows 环境下，由自身进程启动 ffmpeg 子进程会报 `拒绝访问 (os error 5)`。
本项目改为**由工作台自己调用 ffmpeg** 把输入统一转成 16 kHz 单声道 PCM WAV，
再交给 OneAsr——它检测到合规 WAV 会直接复制，不再自行启动 ffmpeg，从而绕开该问题。
识别、对齐与导出的结果完全一致。

---

## 8. 常见问题

**`找不到 ffmpeg`** — 检查第 3.3 节，或在设置页填完整路径。

**`找不到 OneAsr CLI`** — `oneasr_cli` 要填可执行文件本身的完整路径，不是它所在的目录。

**`can_start.ok = false`** — 模型没下齐。重新执行 `oneasr-cli download --model 0.6b`，或用 `status --json` 看缺哪个文件。

**`python` 跳商店 / 版本不对** — 见第 3.1 节的 App 执行别名说明。

**转写结果没有标点** — 检查 `language` 是否与素材语言一致；粤语素材要选 `yue` 而不是 `zh`。

**后端报 `WinError 5` / `os error 5`** — 少数沙箱、CI 或受限终端会禁止服务进程再派生子进程（报错落在 `subprocess.run` 的 `CreateProcess`）。优先改用系统自带的普通终端启动 `python server.py`；若仍受限，可用下面两种已验证的等价方式：

```bash
python -c "import server; server.main()"                              # 起服务
python -c "import server; server.transcribe(server.load_config(), 'demo.mp4')"   # 直接转写一次
```

---

## 9. 目录结构

```
ASR_Workbench/
├── server.py            # 标准库 HTTP 后端
├── web/                 # 原生 HTML / CSS / JS 前端
├── inbox/               # 待转写素材（默认）
├── work/                # 中间 WAV
├── output/              # SRT / TXT 产物（默认）
├── config.example.json  # 配置样例
├── requirements.txt     # 无第三方依赖
├── LICENSE              # MIT
└── README.md
```

---

## 10. 许可证

MIT。见 [LICENSE](LICENSE)。

第三方组件（ffmpeg、OneAsr、Qwen3-ASR、omniASR-CTC）各有自己的许可证，请分别遵守。
