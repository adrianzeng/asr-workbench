# ASR Workbench

> **版本：V1.1（正式版）** — 一个 zip 解压双击就能用：程序随包，模型首次启动自动下载（国内源 + 真实进度条 + 断点续传）。
> 上一版 V1.0 完整保留在 `v1.0` 标签。

一个独立、本地优先、零耦合的语音转写工作台。

把音视频文件放进 `inbox/`，在网页里点一下，得到通顺的 TXT 文稿；需要的话再带上带时间轴的 SRT 字幕或完整时间轴。
默认全程在本机完成，不上传任何音频，不需要账号，不依赖任何笔记软件、知识库或内部系统。
也支持切换到**你自己的云端听写 API**（OpenAI 兼容），适合没有独立显卡的普通电脑。

---

## 0. 先启动起来（三步，不用输命令）

| 你的电脑 | 双击哪个文件 |
|---|---|
| Windows（首版主打） | `先装 Python（双击）.exe` → 再 `启动工作台.bat` |
| macOS / Linux | 先装好 Python 3.12+，终端执行 `bash 启动工作台.command` |

1. 把整个 `ASR_Workbench` 文件夹解压到固定位置（路径里尽量别带中文和空格）。
2. **第一次**双击 `先装 Python（双击）.exe`，一路下一步，务必勾选 `Add python.exe to PATH`。只装这一次。
3. 双击 `启动工作台.bat`。弹出的黑色小窗口**别关**（它就是开关），浏览器自动打开 <http://127.0.0.1:8765>。
4. 第一次会弹出「先准备一下」，点「开始准备」→ 自动下约 2.8GB 听写模型（国内 ModelScope 源、真实百分比、断点续传、逐文件校验）→ 下完自动刷新进主界面。**联网一次，之后断网也能用。**

- 黑窗口关掉＝服务停；重新双击即可，下载会接着上次继续，已下的不丢。
- 已经开着又双击一遍：只把页面再打开一次，不会重复启动。
- 浏览器没弹出来：把 `http://127.0.0.1:8765` 复制到地址栏。
- 断网、磁盘不够、端口被占、校验失败：页面会说人话并给「重试」。
- 详细图文见 `使用说明.txt`；从源码运行用 `python start.py`（`python server.py` 也仍有效）。

---

## 1. 这个项目的边界

- **独立**：自带前端与极薄后端，不依赖任何外部业务系统。
- **零耦合**：不读写你的笔记库、灵感库、Obsidian 仓库或任何其它目录；所有路径都在设置页里配置，默认只碰项目自己的 `inbox/`、`work/`、`output/`。
- **零第三方 Python 依赖**：后端只用 Python 标准库；目录选择框调用系统自带命令，不装 GUI 库。
- **本地优先**：默认用本地模型离线转写（模型下载完成后可完全断网）。**云端引擎默认关闭**；只有当你在设置页明确选中它并填好服务地址后，才会把音频发送到**你自己配置的那个服务**，此外不发起任何外部网络请求。

目前包含「听写 + 打时间轴 + 导出」，以及一个可选的云端听写引擎（见 5.2）。语音助手（实时麦克风与朗读）不在此版本；「改稿引擎」只预留了 OpenAI 兼容接口（见 5.1），**默认关闭、不生效、不联网**。

---

## 2. 环境要求（包里已经带了，不用自己装）

| 组件 | 谁提供 | 说明 |
|---|---|---|
| Python 3.12+ | 包内官方安装器 | 第一次双击装一次，安装时勾 `Add python.exe to PATH` |
| ffmpeg | 包内 `runtime/oneasr/bin/ffmpeg.exe` | GPLv3 essentials build，合规依据见 `THIRD_PARTY_NOTICES.md` |
| OneAsr v1.4.1 | 包内 `runtime/oneasr/` | MIT，上游便携包原样随附 |
| 0.6B 听写 + CTC 对齐权重 | **首次启动自动下载** | 约 2.88GB，ModelScope 国内源，逐文件 sha256 校验 |
| 1.7B 权重（可选） | 切到 1.7B 时提示下载 | 约 3.9GB，下完自动刷新启用 |

只用云端引擎的用户不需要本地权重；但**默认本地引擎，音频不出本机**。
装完之后断网可用：模型就绪判定只读本地文件 + 本地 CLI，从不做网络探测。
后端零第三方 Python 依赖；目录选择框调用系统自带对话框，不装 GUI 库。

---

## 3. 首次准备与下载源

### 3.1 向导在做什么

`GET /api/setup` 会逐个核对 `runtime/oneasr/models/` 下文件的大小与 sha256，缺什么下什么。
`models_manifest.json` 固定了每个文件的 revision / 字节数 / sha256（0.6B 10 个、1.7B 10 个、CTC 6 个）。
其中真正决定「能不能跑」的是每个模型的 3 个核心文件（`config.json`、`model.safetensors`、`tokenizer.json`，CTC 是 5 个）；
`README.md`、`.gitattributes`、`chat_template.jinja` 等 side-car 文件标了 `optional`，缺了不影响识别，也不会因此让你重下 4 GB。
下载器用 HTTP Range 续传、`.part` 临时文件、3 次退避重试、60 秒读超时，校验通过后原子落盘；
已装好的文件不重下。下载在后台线程跑，关掉浏览器也会继续；关掉黑窗口会停，重开接着下。

### 3.2 下载源与以后放网盘

| 配置键 | 默认 | 用途 |
|---|---|---|
| `download_source` | `modelscope` | 改成 `custom` 走自己的镜像 |
| `download_base_url` | 空 | custom 模式下的镜像前缀，目录结构 `{base}/{模型目录名}/{文件路径}` |
| `download_url_template` | ModelScope resolve 模板 | 直链模板，留空用默认 |

**整套 zip 放网盘**：代码零改动 —— 把整包传上去，把分享直链发给用户即可。
WorkBuddy 侧可安装百度网盘连接器（支持上传 + 创建分享链接），但首版一个连接器都不接，
也不写死任何网盘地址。若连模型也要走自己的镜像，按上表改两个字段即可。

### 3.3 出问题怎么自己处理

| 情况 | 页面会说什么 | 你怎么做 |
|---|---|---|
| 断网 / WiFi 掉了 | 连上网络点重试 | 连上 WiFi 点「重试」，已下的不会重下 |
| 硬盘不够 | 空间不足，给搬盘指引 | 把整个文件夹搬到有 10GB 空闲的盘，重新双击，不用重装 |
| 端口被占 | 自动顺延到下一个端口 | 黑窗口和浏览器用的是真实端口，照它显示的打开 |
| 校验失败 | 某个文件没过 sha256 | 自动删掉那一份重下，不用管 |
| 第一次就没网 | 需要联网一次 | 找个能上网的地方跑一次，之后永久离线可用 |

---

## 4. 安装本项目

1. 拿到 `ASR_Workbench_v1.1_win64.zip`，解压出 `ASR_Workbench/` 到一个固定文件夹。
2. 回到上面 **「0. 先启动起来」** 走三步。全过程纯鼠标，不用命令行、不用手填路径。
3. 想从源码跑：`git clone https://github.com/adrianzeng/asr-workbench.git`，然后 `python start.py`。

`config.json` 不用手动建：首次启动或首次保存设置时自动生成；它已被 `.gitignore` 忽略。
**发布版里所有路径都是相对路径**，整个文件夹搬到别的盘、拷到另一台电脑都能直接跑。
端口在配置里改（默认 `8765`）。服务只监听 `127.0.0.1`，不对外网开放。

---

## 5. 配置说明

| 字段 | 说明 | 默认 |
|---|---|---|
| `ffmpeg` | ffmpeg 可执行文件；包内已带 | `./runtime/oneasr/bin/ffmpeg.exe` |
| `oneasr_cli` | OneAsr CLI；包内已带 | `./runtime/oneasr/oneasr-cli.exe` |
| `oneasr_data_root` | OneAsr 数据根（模型在它下面的 `models/`） | `./runtime/oneasr` |
| `inbox_dir` | 放待转写音视频的目录，可在「① 选素材」点按钮选（弹出的是资源管理器那种窗口，左侧有桌面 / 下载 / 文档） | `./inbox` |
| `output_dir` | 产物根目录；每个素材会在下面单独建同名子文件夹 | `./output` |
| `work_dir` | 中间 WAV 目录；没被输出的产物也归档到这里 | `./work` |
| `language` | 识别语言，如 `zh` / `yue` / `en` | `zh` |
| `asr_engine` | `local`（默认，不上传）/ `cloud`（上传音频到配置的服务） | `local` |
| `asr_model` | 本地听写模型：`0.6b` 或 `1.7b`（后者需先下载权重） | `0.6b` |
| `aligner` | `ctc` 或 `qwen` | `ctc` |
| `backend` | `auto` / `cpu` / `gpu`。没有独显的普通笔记本选 `cpu`，0.6B 模型照样能跑，只是慢一些 | `auto` |
| `output_mode` | 产物留哪些：`txt` / `txt_srt` / `all`，见下面的表 | `txt_srt` |
| `cloud_asr_base_url` | 云端引擎的 OpenAI 兼容地址（含 `/v1`） | 空 |
| `cloud_asr_api_key` | 云端引擎的 API Key；只存本机 `config.json`，返回浏览器时脱敏 | 空 |
| `cloud_asr_model` | 云端听写模型名 | 空 |
| `rewrite_engine` | `off`（默认）/ `openai`。**接口预留，当前不生效** | `off` |
| `rewrite_base_url` | OpenAI 兼容服务的 `/v1` 地址（云端，或本机 Ollama / LM Studio） | 空 |
| `rewrite_api_key` | API Key；只存本机 `config.json`，返回浏览器时脱敏 | 空 |
| `rewrite_model` | 模型名，如 `qwen3-vl-8b`、`deepseek-chat` | 空 |
| `port` | 本地服务端口 | `8765` |
| `download_source` | `modelscope` / `custom` | `modelscope` |
| `download_base_url` | 自有镜像前缀（custom 时用） | 空 |
| `download_url_template` | 模型直链模板 | 空（用内置默认） |
| `auto_download` | 首次启动自动补齐缺失模型 | `true` |

**所有目录默认填相对路径，以项目根目录为基准** —— 这样整个文件夹可以任意搬动。确实要指向别处时才填绝对路径（例如把素材目录指到「下载」文件夹）。

### 产物文件：为什么有一个很大的 JSON

在「③ 拿文件 → 要哪几个文件」里三选一，选完立即保存，下次转写生效：

| 选择 | 输出目录里会有什么 | 适合谁 |
|---|---|---|
| 只要文稿 | `<素材名>.txt` | 只要文字稿，拿去改稿、喂给 AI |
| 文稿 + 字幕（默认） | 再加 `<素材名>.srt` | 还要把字幕传进剪辑软件或平台 |
| 全部 | 再加 `<素材名>.timeline.json` | 要给程序用，或以后想不重跑就重出字幕 |

那个 `.timeline.json` 是**打轴（对齐）**算出来的逐句、逐字时间数据，普通做稿子用不到，体积最大（4 分半的素材约 110 KB，1 小时能到 1.5 MB 上下）。SRT 和 TXT 其实都是从它渲染出来的，所以它本身不是垃圾，只是不必出现在产物目录里。

三种模式**都不会删除任何文件**：没被输出的会移到 `work/kept/<素材名>/`。以后想补出字幕，不用重新跑一遍转写，直接：

```bash
oneasr-cli render --timeline work/kept/<素材名>/<素材名>.timeline.json
```


### 5.1 改稿引擎（接口预留）

这是一个**只留接口、不接线**的功能位：配置字段、界面表单、后端扩展点（`rewrite.py`）和 API 都已就位，但**本版本不会发起任何网络请求**，也不会改动转写出来的文稿。默认 `off`。

| 现状 | 说明 |
|---|---|
| 能做的 | 保存 Base URL / API Key / 模型名；界面显示当前状态；`GET /api/rewrite` 查状态、`POST /api/rewrite` 拿到原样返回的文本与明确状态 |
| 不做的 | 不请求 `/chat/completions`、不装任何 SDK、不引入额外依赖、不上传任何内容 |

将来要启用，只需实现 `rewrite.py` 里的 `rewrite_draft()`（文件内已附标准库 `urllib.request` 的调用示例），配置、界面、接口都不用改。同一个 OpenAI 兼容口子既能接云端（DeepSeek / 通义 / OpenAI），也能接本机 Ollama / LM Studio 里跑的模型。

**隐私约定（将来启用时必须遵守）**：只发送**文字稿**、绝不上传音频；界面要显式提示文本将发给哪个服务；默认必须保持关闭。

### 5.2 云端听写引擎（可选，默认关闭）

针对**没有独立显卡的普通电脑**（轻薄本、办公本），本项目除了本地模型，还内置一个**OpenAI 兼容**的云端听写引擎：

- 接口协议：`POST {base_url}/audio/transcriptions`，multipart 上传整段 16 kHz WAV，带 `Authorization: Bearer <key>`，请求 `verbose_json` 以拿到分段时间。
- 在「② 出稿子」里展开「识别设置」，把「听写引擎」选成「云端 API（会把音频传出去）」，再填 Base URL / 模型名 / API Key。切换引擎时界面会显式提示**音频将上传到该服务**；选回「自己电脑上跑」后音频重新只在本机处理。
- API Key 只存本机 `config.json`（gitignored），返回浏览器一律脱敏。
- 服务方不返回分段时间时，SRT 会以「整段时间轴 + 全文」**如实**输出，不伪造时间戳。
- 仍然零第三方依赖：上传用 Python 标准库 `http.client` 分块流式发送，不装 SDK。

**隐私边界**：本地引擎下音频一个字节都不出本机；云端引擎下音频只发送到**你自己填的那个服务**，本项目不内置任何默认云端地址，也不收集任何数据。

如果你打算自己对外提供听写 API（例如给读者/客户按量收费），请把密钥签发、账号、计费放在**你自己的服务端**，本客户端只需要一个 Base URL + Key + 模型名；不要把主密钥硬编码进开源代码。

---

## 6. 使用

1. 把音视频文件放进 `inbox/`；也可以在「① 选素材」点 **「选个文件夹…」** 把 `inbox_dir` 指到本机任意目录，或手填路径后点「应用并刷新」。
2. 文件列表里**勾选要转的文件**，点「全选」可以一次全勾上 —— 8 个、10 个、100 个都行，然后点「开始转文字（N 个）」。
3. 它们会**排成一队，一个一个慢慢出稿**，不用守着：关掉浏览器也会继续跑，回来刷新页面就能接着看进度。每完成一份，稿子会自动显示在「② 出稿子」；点队列里「已完成」的那一行，可以回看任意一份。
4. 想中途收手点「停止这一批」：**当场就停**（正在转的那个进程会被掐掉，通常一秒内），排队中的直接跳过，已经出稿的全部保留。
5. 「③ 拿文件」显示当前正在看的那份放在哪，点「复制文字稿」就能直接拿去用。

> 批量任务**顺序执行**（一次只跑一个，避免几个模型抢显存）；队列状态只存在服务进程里，服务关掉后进度记录会清空，但**已经产出的文件都在 `output/` 里，不会丢**。
> 想从脚本或 Agent 调度：`POST /api/jobs {"names": [...]}` 提交、`GET /api/jobs` 查进度、`GET /api/jobs/result?name=...` 取某份稿子、`POST /api/jobs/cancel` 停止。单文件老接口 `POST /api/transcribe` 仍然保留。
>
> **已知限制（V1.0）**：批量进度只保存在服务进程内存里，服务中途关闭后进度列表会清空（已产出的文件不会丢，重新勾选即可继续）；语音助手（麦克风输入 / 朗读回答）与改稿引擎留到下一版。

**产物按素材分文件夹存放**，不会混在一起：

```
output/
├── demo/
│   ├── demo.srt
│   ├── demo.txt
│   └── demo.timeline.json
└── interview/
    ├── interview.srt
    ├── interview.txt
    └── interview.timeline.json
```

输出目录同样可以用「③ 拿文件」里的「选个文件夹…」改到别处。

### 关于混合语言（中英夹杂、粤语+英语……）

1.7B 与 0.6B 听写模型都支持 **30 种语言 + 22 种中文方言**（普通话、英语、粤语、日语、韩语、闽南语、吴语、四川话等），官方明确支持**同一段话里几种语言混着说**（code-switching）。但**本工作台不做自动语种判断**：`server.py` 会把「说的哪种话」这一档固定传给听写程序。中英夹杂我们实测过，选「中文」照样能把英文词一起写出来；整段以英文、日文或粤语为主时，请手动切到对应语言，识别会更稳。

粤语+英语、英语+日语、日语+韩语这类组合，涉及的语言都在官方支持清单里；但本项目**只对中英夹杂做过实测**，其它组合没有逐一对着音频验证，不保证效果。遇到识别不准，把「说的哪种话」切成占篇幅最多的那一种再跑一遍。

另外：「打时间轴」用的对齐器语言覆盖比听写模型窄，混合语言时字幕的时间点可能不如单语准；只要文字稿不受影响。界面「识别设置」里也放了同样的说明。

完整的 30 种语言与 22 种方言清单，在界面「② 出稿子 → 识别设置 → 能听懂哪些话？」里点「展开完整清单」。默认收起，不占主界面，想查的时候点两下就能看到。

**0.6B 和 1.7B 是同一个系列**（Qwen3-ASR 的两档大小，约 6 亿 / 17 亿参数），语言支持范围完全相同，区别只在精度、断句、速度和资源占用：1.7B 更准、长句更连贯，但慢一倍左右、模型约 4.1 GB；0.6B 约 1.5 GB，普通笔记本纯 CPU 也能跑。本机实测 4 分 38 秒素材，显卡下分别约 15 / 30 秒，纯 CPU 都在 190 秒上下；同一素材两份文稿不完全一样，主要差在断句和个别字。界面「识别设置 → 0.6B 和 1.7B 有什么区别」里有一张对照表。

**怎么确认真的切过去了**：切完在「听写模型」下面会有一行小字「现在会用：1.7B 更准听写模型 · Qwen3-ASR-1.7B-hf」，模型列表里对应的那一行会标上「正在用」。每份稿子转完，「② 出稿子 → 用的引擎」也会写明这次跑的是哪个模型目录 —— 那是从实际执行的那条命令里带回来的，不是下拉框的显示值。想眼见为实，切到 1.7B 转同一段素材，耗时大约是 0.6B 的两倍，稿子的断句也会不一样。

### 6.1 「选择文件夹」是怎么工作的

浏览器出于安全限制拿不到本机绝对路径，所以这个按钮由后端调用系统自带的图形对话框：

| 系统 | 调用 | 需要额外安装吗 |
|---|---|---|
| Windows | 资源管理器同款目录窗口（`IFileDialog`）；调不出来时自动退回旧式对话框 | 不用，Win10/11 自带 |
| macOS | `osascript` 的 `choose folder` | 不用，系统自带 |
| Linux | `zenity --file-selection --directory` | 需要 `zenity`（没有就手填路径） |

项目因此**不需要任何第三方 Python 包或 GUI 库**。对话框由运行 `start.py`（或 `server.py`）的那个进程弹出，可能出现在浏览器窗口后面——点完按钮没反应时看一眼任务栏。选完点「选择文件夹 / 确定」会自动填回输入框并保存生效；点「取消」或 3 分钟不操作，原路径不变。该接口只监听 `127.0.0.1`，不对外网开放。

支持常见音视频格式，**纯音频和视频一视同仁**：

- 音频：wav / mp3 / flac / m4a / aac / ogg / opus / wma
- 视频：mp4 / mkv / mov / webm / avi / flv / ts / m4v / mpeg / mpg / wmv / 3gp

不管哪种，后端都先用 ffmpeg 抽成 16 kHz 单声道 PCM WAV 再交给听写模型，所以 MP3 不需要任何额外设置。


---

## 7. 为什么后端要先转一道 WAV

OneAsr 在部分 Windows 环境下，由自身进程启动 ffmpeg 子进程会报 `拒绝访问 (os error 5)`。
本项目改为**由工作台自己调用 ffmpeg** 把输入统一转成 16 kHz 单声道 PCM WAV，
再交给 OneAsr——它检测到合规 WAV 会直接复制，不再自行启动 ffmpeg，从而绕开该问题。
识别、对齐与导出的结果完全一致。

---

## 8. 常见问题

**`找不到 ffmpeg`** — 发布包里自带，检查 `runtime/oneasr/bin/ffmpeg.exe` 是否被误删；从源码跑时才需要自己装或在设置页填路径。

**`找不到 OneAsr CLI`** — 发布包里自带 `runtime/oneasr/oneasr-cli.exe`；从源码跑时，`oneasr_cli` 要填可执行文件本身，不是它所在目录。

**首次准备卡住 / 模型没下齐** — 页面「模型管理」会列出缺哪个文件，点「重试」即可；只补缺的，不会重下 4GB。断网时先连上 WiFi。

**选了 1.7B 后转写失败** — 1.7B 是另一份独立权重（约 3.9GB），切过去时会弹出下载提示；等进度条走完、页面自动刷新后再跑。

**选了云端引擎后转写失败** — 先确认 Base URL 填的是含 `/v1` 的完整地址（本项目会自动在其后拼接 `/audio/transcriptions`）、模型名是服务方提供的听写模型；再检查该服务是否真的兼容 OpenAI 的 audio 接口。报错信息里会带上服务方返回的 HTTP 状态码。

**`python` 跳商店 / 版本不对** — 见第 3.1 节的 App 执行别名说明。

**点「选个文件夹…」没弹出窗口** — 窗口可能在浏览器后面，看一眼任务栏；Linux 需先装 `zenity`；若服务是在无图形会话的后台 / CI 里启动的，改用普通终端执行 `python start.py`，或直接手填路径。

**转写结果没有标点** — 检查 `language` 是否与素材语言一致；粤语素材要选 `yue` 而不是 `zh`。

**后端报 `WinError 5` / `os error 5`** — 少数沙箱、CI 或受限终端会禁止服务进程再派生子进程（报错落在 `subprocess.run` 的 `CreateProcess`）。优先改用系统自带的普通终端执行 `python start.py`；若仍受限，可用下面两种已验证的等价方式：

```bash
python -c "import server; server.main()"                              # 起服务
python -c "import server; server.transcribe(server.load_config(), 'demo.mp4')"   # 直接转写一次
```

---

## 9. 目录结构

```
ASR_Workbench/
├── 先装 Python（双击）.exe  # 仅发布包里有，第一次装一次
├── 启动工作台.bat           # Windows 双击启动
├── 启动工作台.command      # macOS 双击启动（Linux 用 bash 跑）
├── 使用说明.txt             # 给新手看的图文步骤
├── THIRD_PARTY_NOTICES.md  # 第三方组件与许可说明
├── THIRD_PARTY_LICENSES/   # MIT / GPLv3 / BSD-2 / PSF 全文
├── start.py                # 启动器：开浏览器、查端口、拉起服务
├── first_run.py            # 首次启动：写全相对配置、建 runtime 目录
├── downloader.py           # 标准库断点续传下载器
├── models_runtime.py       # 模型下载状态机
├── models_manifest.json    # 模型文件清单（revision / size / sha256）
├── build_release.py        # 打 zip + 全量校验（纯标准库）
├── jobs.py                 # 批量任务队列
├── server.py               # 标准库 HTTP 后端
├── cloud_asr.py / rewrite.py
├── web/                    # 原生 HTML / CSS / JS 前端
│   └── author-qr.png       # 作者微信二维码
├── runtime/oneasr/         # 随包程序（模型不随包，首次下载到这里）
│   ├── oneasr-cli.exe · oneasr.exe · bin/ffmpeg.exe
│   └── models/ · output/ · runs/
├── release_assets/         # 构建输入（Python 安装器，仅维护者有）
├── dist/                   # 构建产物 zip + SHA256SUMS.txt
├── inbox/ · work/ · output/   # 素材、中间文件、产物（默认相对路径）
├── config.example.json · requirements.txt · LICENSE · README.md
└── config.json             # 本机配置，gitignored，自动生成
```

### 9.1 作者信息

顶栏右侧「关于作者」里的文字在 `web/app.js` 顶部的 `AUTHOR_INFO`；微信二维码是 `web/author-qr.png`
（从作者给的截图里裁出二维码主体、去掉名字与底部说明文字，四周留了白边以便扫码）。
卡片里**只放二维码**，没有微信号、邮箱或主页。改名字或换码，替换这两处即可，不需要动 HTML。

---

## 10. 打包与托管

`python build_release.py` 产出 `dist/ASR_Workbench_v1.1_win64.zip` 和 `SHA256SUMS.txt`。
纯标准库、不需要 git。打包前逐条校验，任一失败即中止：

1. `config.example.json` 无盘符 / 无 URL；`.bat` 全 CRLF、`.command` 全 LF；
2. 随包 ffmpeg 的 `-version` **不含** `--enable-nonfree`（否则不可再分发）；
3. README 不再把下 OneAsr、敲下载命令、手填路径写成用户必做步骤；
4. zip 里没有 `config.json`、模型权重、`.part`、嵌套压缩包；`runtime/oneasr/models/` 只有 `.keep`；
5. 顶层只有 `ASR_Workbench/` 一个目录，`使用说明.txt` 与 `THIRD_PARTY_NOTICES.md` 在根；
6. 三个 exe 与 Python 安装器逐字节 sha256 与源文件一致。

zip 里是**代码 + 程序 + Python 安装器**，不含模型（首次启动自动下）。
托管按 3.2：整套 zip 放网盘 / Release / 对象存储，把直链发用户，代码零改动；首版不接任何连接器。

---

## 11. 许可证

MIT。见 [LICENSE](LICENSE)。

第三方组件（OneAsr、FFmpeg、imageio-ffmpeg、Python、Qwen3-ASR、omniASR-CTC）各有自己的许可证，**逐项来源、许可全文与再分发依据见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)**。
模型权重不随包分发，首次启动时由用户自行从 ModelScope 下载。
