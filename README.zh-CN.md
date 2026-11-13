# ElevenLabs-Auto-Ducking-Video-Audio-Mixer

**音乐退一步，让漫剧台词站到前面。**

[English](README.md) · 简体中文 · 原项目 ElevenLabs Auto Ducking Demo v0.2

Dialogue Duck 专注一个常见问题：背景音乐一响，角色台词就听不清。它把 ElevenLabs 的视频配乐与 Scribe 讲话时间戳，接到本地 FFmpeg 混音流程中，让新增背景音乐在讲话时降低、停顿时恢复。

## 适合哪些作品

| 场景 | 使用方式 |
|---|---|
| 漫剧 / 动态漫画 | 角色对白期间压低新增音乐，间隙恢复氛围 |
| 知识口播 / 教程 | 减少背景音乐对连续讲解的遮挡 |
| 剧情短视频 / 预告 | 为对白密集片段制作更容易听清的配乐版本 |
| 配乐方案验证 | 用同一条视频比较不同音量和恢复速度 |

它是一个聚焦人声避让的轻量工具。需要完整多轨时间轴编辑时，可以关注同系列的 SoundFlow Studio。

## 当前功能

- 内置视频、音乐和讲话时间戳样例，无需 Key 即可完成本地混音。
- 上传视频，选择导入已有音乐或通过 ElevenLabs Video-to-Music 生成音乐。
- 通过 Scribe 获取词级时间戳，也可由 API 提交手动讲话区间。
- 调整基础音乐音量、讲话压低幅度、短停顿合并、提前压低、结束保持和渐变恢复。
- FFmpeg 在本机生成可预览、可下载的 MP4。
- 保留独立混音核心与本地 worker 示例，便于研究后续任务化处理。

界面目前以中文为主；本仓库提供中英文文档，尚未提供完整英文界面。

## 技术栈与环境

| 层 | 实现 |
|---|---|
| 界面 | 原生 HTML / CSS / JavaScript 单页 |
| 服务 | Python、FastAPI、Uvicorn、Pydantic |
| 在线能力 | HTTPX → ElevenLabs Video-to-Music、Scribe v2 |
| 本地处理 | FFmpeg / ffprobe、讲话区间合并与音量包络 |
| 存储 | 项目根目录 `runtime/`，可由 `DUCKING_DATA_DIR` 修改 |
| 推荐环境 | Python 3.11 / 3.12、FFmpeg、桌面浏览器；无需数据库 |

## 快速开始

下载或克隆仓库，进入含 `app.py`、`requirements.txt` 的根目录。现有文件夹名称为 `elevenlabs-auto-ducking-demo`。

### 安装依赖

建议 Python **3.11 或 3.12**，并为每个项目单独建立虚拟环境。本项目是 Python 应用，**不需要 Node.js、npm 或独立数据库**。建议使用较新的 Chrome、Edge、Firefox 或 Safari；实际媒体解码能力取决于浏览器。

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

如果 PowerShell 的执行策略不允许激活，可直接使用 `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`，后续启动命令也使用该 Python 路径。

FFmpeg 安装示例：

```bash
# macOS（已安装 Homebrew）
brew install ffmpeg
# Ubuntu / Debian
sudo apt-get update
sudo apt-get install ffmpeg
```

Windows 请安装 FFmpeg 并将其 `bin` 目录加入 PATH。新开终端后确认：

```bash
ffmpeg -version
ffprobe -version
```

### 启动本地服务

不需要真实 AI 时直接启动：

```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

需要视频配乐或 Scribe 时，在启动前设置：

```bash
export ELEVENLABS_API_KEY="<your-elevenlabs-api-key>"
# 可选：改变本地数据目录
# export DUCKING_DATA_DIR="/absolute/path/to/jobs"
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

PowerShell 对应设置为 `$env:ELEVENLABS_API_KEY="<your-elevenlabs-api-key>"`，再执行同一启动命令。

打开 **http://127.0.0.1:8765**；API 文档在 **http://127.0.0.1:8765/api/docs**。**程序不自动加载 `.env`**；`.env.example` 仅用于说明变量。macOS 可在配置好环境变量的终端执行 `./启动_Mac.command`。

## 先用内置样例感受变化

1. 点击“使用内置样例”，试听原视频和背景音乐。
2. 调整基础音乐音量和讲话时的压低幅度。
3. 调整停顿合并和恢复速度，观察不同节奏的效果。
4. 执行 FFmpeg 混音，试听并下载结果 MP4。

真实素材路线：**上传视频 → 上传或生成音乐 → 获取 Scribe 讲话区间 → 调整参数 → 本地混音 → 下载 MP4**。

## 参数怎么理解

| 参数 | 对听感的影响 |
|---|---|
| 基础音乐音量 | 没有讲话时的背景音乐响度 |
| 压低幅度 | 讲话时相对降低多少；过大会造成明显抽吸感 |
| 停顿合并 | 把相邻短停顿视作一段讲话，减少反复起伏 |
| 提前压低 / 结束保持 | 给句首和句尾留出空间 |
| Attack / Release | 音乐降低、恢复的速度；结合对白节奏试听 |

## 数据、费用和实际边界

导入和混音在本机完成。点击生成音乐或转录时，视频文件会发送给 ElevenLabs，包含文件中的音画内容；描述也会随音乐请求发送。Key 从后端环境读取，仅通过 HTTPS 认证头发给 ElevenLabs。仓库忽略 `.env`、`runtime/` 与虚拟环境；没有独立遥测上报代码，但不承诺上游零留存。

真实 API 请求可能收费，短样片更适合初次验证。项目中的 `scripts/live_smoke.py` 默认只检查身份；**带 `--paid` 才会对短样例调用付费接口**，请阅读脚本后再执行。

当前单视频限 **100 MB / 600 秒**。本工具降低的是新加入的背景音乐，**不会从原音轨中分离或压低已混入的旧音乐**；也不做降噪、说话人分离、自动翻译或声音克隆。人声识别可能漏判，应结合试听复核。无登录、多租户、自动清理和生产队列。

## 二次开发入口

| 路径 | 职责 |
|---|---|
| `app.py` | 上传、配乐、识别、时间轴与渲染 API |
| `core.py` | 时间戳合并、媒体分析、音量包络和混音 |
| `elevenlabs_client.py` | 官方 API 客户端 |
| `static/index.html` | 本地交互页面 |
| `fc_worker.py` / `fc_job.example.json` | 本地执行器与任务格式示例 |
| `tests/` | 核心流程与模拟请求测试 |

开发测试：`python -m pytest -q`。本地 worker 示例：`python fc_worker.py fc_job.example.json`。仓库中的阿里云 FC 文档是迁移思路，不代表当前服务会创建云函数或上传 OSS。

## 参考

- [ElevenLabs Video-to-Music](https://elevenlabs.io/docs/api-reference/music/video-to-music)
- [ElevenLabs Scribe](https://elevenlabs.io/docs/api-reference/speech-to-text/convert)
- [FFmpeg 文档](https://ffmpeg.org/documentation.html)

## 本地部署与二次开发

以上命令启动的是**本机单用户服务**。终端保持运行即可使用，按 `Ctrl+C` 停止；重启时进入同一目录，激活同一虚拟环境，再执行启动命令。不同项目使用相同端口时，请停止前一个服务，或把 `--port` 改为未占用端口。

如需让服务长期运行，可由进程管理器管理同一条 Uvicorn 命令。正式向团队或公网提供服务之前，需要增加身份认证、用户数据隔离、任务队列、用量限制、日志脱敏和文件清理。当前仓库没有实现这些生产部署能力。

## 常见问题

| 问题 | 排查方向 |
|---|---|
| 找不到 `uvicorn` 或模块 | 确认已激活虚拟环境，并在项目根目录执行 `python -m pip install -r requirements.txt` |
| 找不到 FFmpeg / 无法读取媒体 | 检查 `ffmpeg -version`、`ffprobe -version`，安装后重启终端 |
| API 提示 401 / 403 | 检查本机 Key、对应产品权限和账号状态；不要把完整 Key 发到 Issue |
| API 提示 429 / 生成超时 | 检查额度、并发与网络；先用短素材验证，确认上游任务状态后再决定是否重新提交 |
| 浏览器无法播放 | 检查浏览器支持的封装与编码；可以下载到本地播放器检查 |
| 修改环境变量后仍未生效 | 在配置所在终端重启 Uvicorn |

## 参与改进

欢迎提交复现步骤、已脱敏报错和功能建议。漫剧对白被音乐遮住、译配字幕偏移、音乐情绪不匹配等具体场景，比单纯写“效果不好”更有帮助。请写明系统、Python / FFmpeg 版本、输入格式和最短复现流程；真实素材请先确认分享权限。

代码采用 [MIT License](LICENSE)。API 使用、生成内容、音视频素材与依赖软件的授权另行适用。

## ElevenLabs 接入与价格咨询

这个项目由独立开发者维护，希望用一个能实际操作的小工具，帮助漫剧团队、视频创作者和产品开发者理解 ElevenLabs 的能力。

如果你正在做**漫剧配音、短剧出海、视频配乐、音效制作、语音产品或批量 API 集成**，欢迎联系我，一起评估适合的产品、工作流和接入方式。我也可以提供**有价格优势的 ElevenLabs 方案报价**，具体方案、适用条件和价格以实际需求及单独报价为准。

**咨询邮箱：[lcnwys@gmail.com](mailto:lcnwys@gmail.com)**

为了更快给出建议，邮件中可以写明：

- 你在做什么内容或产品，以及一段已脱敏的需求说明。
- 每月预计视频/音频分钟数、目标语言、团队规模和是否需要 API。
- 希望先做样片验证，还是正在准备上线。

请不要在邮件或公开 Issue 中发送 API Key、账号密码或未获授权的客户素材。功能问题适合提 Issue；商务和价格咨询请发邮件。

> 这是独立社区项目，并非 ElevenLabs 官方产品。咨询和报价也不代表官方背书；ElevenLabs 的名称和商标归其权利人所有。
