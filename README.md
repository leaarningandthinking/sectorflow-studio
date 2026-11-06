# SectorFlow Studio · 资金流向视频工作台

在自己的电脑上获取大盘、行业或概念资金流数据，预览分钟走势并导出竖屏视频、视频封面。工作台只监听本机 `127.0.0.1`，默认端口 `8765`。

## 功能

- 沪深两市主力资金流向，行业与热门概念走势图切换。
- 行业先剔除31个一级行业，再取收盘净流入前8、净流出前7；上游候选不足时按实际数量展示，后台显示说明。概念取净流入前10。
- 按收盘入选名单回放全天；缺失分钟保留空值，不补零、不插值。纵轴使用最终去重曲线的全天范围，回放过程中固定。
- 15色实线、端点右侧动态标签和避让；行业名称隐藏末尾 II/Ⅱ，原始数据不变。
- 1080×1920 MP4，默认21秒：15秒行情、1秒收盘停留、5秒完整片尾。行情顶部90px、底部220px安全区，片尾铺满。
- 本地音乐开关默认开启，选择音乐后覆盖整个视频（含片尾），结束淡出；未选择时阻止视频导出。关闭则只保留片尾原声。
- 独立视频封面，日期默认北京时间当天，可手选；支持1200×1600和1080×1920。导出 JPG 严格不超过500,000字节，优先保留尺寸，必要时等比例缩小。
- 思源黑体简体可变字体、ECharts 均随项目本地加载，预览和渲染无需访问字体/CDN网站。首次安装依赖和真实取数仍需联网。

## 安装与启动

需要 **Python 3.10或更新版本、FFmpeg和ffprobe**。推荐Python 3.12。操作系统须满足当前Playwright要求，见[官方说明](https://playwright.dev/python/docs/intro#system-requirements)。

### Mac

1. 安装Python及FFmpeg。已有Homebrew时可运行：`brew install python ffmpeg`。
2. 下载项目ZIP并解压到可写文件夹，双击 `安装并启动.command`。
3. 首次启动会创建项目专用 `.venv`、安装依赖及Chromium，然后打开浏览器。

如果系统未直接允许启动，可在项目文件夹终端运行：

```bash
python3 bootstrap.py
```

### Windows

1. 安装Python，安装时勾选加入PATH。
2. 从[FFmpeg官方入口](https://ffmpeg.org/download.html#build-windows)下载Windows构建，解压后把包含 `ffmpeg.exe`、`ffprobe.exe` 的 `bin` 文件夹加入PATH，再打开新的终端。
3. 解压项目，双击 `安装并启动.bat`。首次自动安装项目依赖及Chromium，然后打开浏览器。

也可在项目文件夹运行：

```powershell
py -3 bootstrap.py
```

保持启动窗口打开，按Ctrl+C停止服务。已有服务占用8765时可以运行 `python bootstrap.py --port 8766`。只检查环境：`python bootstrap.py --check`；启动不打开浏览器：`python bootstrap.py --no-browser`。

首次安装需要网络，Chromium下载较大；不要把他人或其他系统创建的 `.venv` 复制过来，启动工具会在本机建立环境。

## 开始使用

打开 `http://127.0.0.1:8765/`。首次没有历史缓存时，可切换“模拟演示”体验全部流程；模拟数据会明确标记。

使用真实数据时选择日期、数据源、行业或概念，再点击“获取／重新获取接口数据”。设置时长、本地音乐，播放预览后导出。视频封面使用上方独立“视频封面”标签，无需接口数据或音乐。

默认API地址位于 `data_source.py`，使用POST JSON：`{"date":"YYYYMMDD"}`。可在启动前通过环境变量覆盖，**不会自动读取.env文件**：

Mac：
```bash
export SECTORFLOW_API_BASE="https://your-host.example/ai-gateway/api"
python3 bootstrap.py
```

Windows PowerShell：
```powershell
$env:SECTORFLOW_API_BASE="https://your-host.example/ai-gateway/api"
py -3 bootstrap.py
```

| 数据 | 默认TOP源 | 兼容源 |
| --- | --- | --- |
| 沪深两市 | fund_flow_min | fund_flow_min |
| 行业 | fund_flow_block_top | fund_flow_block |
| 概念 | fund_flow_plat_top | fund_flow_plat |

默认地址来自本项目使用的接口环境，项目公开不意味着该服务向所有人开放，也不保证可用性或数据完整性。需自行具备接口访问权限。接口失败不会静默改用其他源或模拟数据。

TOP接口两侧按代码合并去重，净额保留原始符号，金额从元转换为亿元，不做再次累加。行业排名只限上游实际返回的候选范围，不代表全市场行业排名。预览与导出绑定同一快照。

## 手动安装及导出

```bash
python -m venv .venv
```

Mac的Python路径为 `.venv/bin/python`，Windows为 `.venv\Scripts\python.exe`。使用该Python运行：

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
python server.py
```

以上 `python` 指项目虚拟环境的Python。命令行导出示例：

```bash
python export.py --date 2026-11-06 --mode demo --source top --type video --duration 15 --music your-music.wav
```

CLI的 `--duration` 是行情时长，另加1秒收盘停留和5秒片尾；工作台输入的是总时长。`--category concept` 可切换概念。CLI未传 `--music` 不加背景音乐。

## 目录与发布

- `server.py`：本机服务；`data_source.py`：数据接入、过滤、缓存与快照。
- `web/`：工作台、封面、图表库、字体及运行必需的模板素材。
- `export.py`、`audio.py`、`outro.py`：渲染、全程音乐和片尾拼接。
- `bootstrap.py`：跨平台安装启动；`tests/smoke_release.py`：离线模拟数据验收。
- `data/`、`music/`、`output/`：运行时创建，不提交到仓库。

此仓库用于下载后在本机运行。GitHub Pages不能运行本项目Python后台。不要直接把无登录校验的本机服务暴露为公网多人服务。

兼容性检查使用GitHub Actions的macOS和Windows运行器。检查内容包括字体、两个尺寸的500KB封面、模拟数据走势图及带音乐完整视频导出。实机表现仍会受到硬件和系统环境影响。

## 授权与素材

本项目Python、HTML、CSS、JavaScript自有代码使用MIT许可证，详见 `LICENSE`。第三方字体和库不改用MIT：

- **思源黑体 Source Han Sans SC**：Adobe官方2.005版本，完整未修改的简体中文可变WOFF2，SIL OFL 1.1；授权文件 `licenses/SourceHanSans-OFL.txt` 随包保留。
- **Apache ECharts 5.6.0**：Apache License 2.0；许可证及NOTICE位于 `licenses/`。
- 片尾视频、品牌标识和封面底图属于单独的视觉素材，不包含在代码MIT授权内，权利归相应权利人；公开仓库不授予第三方商标或素材的额外使用许可。复用品牌模板前请取得适用授权，或替换为自有素材。
- 本地音乐由使用者自行选择，仓库不提供音乐文件。

项目生成的文字统一使用上述思源黑体；预先制作的片尾视频和图片内已有文字不由代码替换，其字体授权需按原素材核实。完整组件来源见 `THIRD_PARTY_NOTICES.md`。
