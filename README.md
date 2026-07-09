# B站收藏夹/稍后再看 → 文字归档工具

抓取 B站"收藏夹"和"稍后再看"里的视频，用本地 Whisper 模型转录语音，再用 LLM 整理成"优化后原文"+"内容概括"，输出为 Obsidian 兼容的 Markdown 文件。

## 快速开始

```bash
git clone git@github.com:siweili-1113/bilibili-sync.git
cd bilibili-sync

# 一键安装（创建 venv + 安装依赖 + 生成 .env）
./setup.sh

# 编辑配置
nano .env

# 试跑 5 个视频
source .venv/bin/activate
python3 -m src.main run --limit 5
```

## 配置

编辑 `.env` 文件，填两个值：

```
BILIBILI_SESSDATA=  ← 浏览器 F12 → Console 输入:
                       document.cookie.split(';').filter(c=>c.includes('SESSDATA'))

LLM_API_KEY=        ← DeepSeek/OpenAI 的 API Key
```

## 命令

| 命令 | 说明 |
|---|---|
| `python3 -m src.main status` | 查看处理进度 |
| `python3 -m src.main sync --limit 10` | 同步 10 个视频元数据 |
| `python3 -m src.main process` | ASR 转录 + LLM 整理 |
| `python3 -m src.main export` | 导出 Markdown |
| `python3 -m src.main run --limit 10` | 一键全流程 |

常用选项：`--source watch_later`（只看稍后再看）、`--source favorites`（只看收藏夹）、`--limit N`（限制处理条数）。

## 工作流程

```
sync（拉元数据）
  → ASR（下载音频 → Whisper 转录 → 删音频）
  → LLM（DeepSeek 整理标点分段 + 生成结构化摘要）
  → export（Obsidian Markdown）
```

## 输出目录

```
output/
├── 收藏夹/
│   └── 默认收藏夹/
│       ├── 视频标题.md
│       └── ...
└── 稍后再看/
    └── 视频标题.md
```

每个 `.md` 包含 YAML frontmatter 元数据 + 内容概括 + 完整文字记录。

## 依赖

- Python >= 3.10
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)（本地语音识别）
- DeepSeek / OpenAI 兼容 API
- Whisper small 模型（首次运行自动下载 ~500MB，国内走 HF 镜像）

不需要 GPU，Apple Silicon MPS 加速约 4-5x 实时速度。

## 清理

```bash
./cleanup.sh  # 卸载依赖 + 删除模型 + 清临时文件
```

## 项目结构

```
bilibili-sync/
├── setup.sh            # 一键安装
├── cleanup.sh          # 清理环境
├── requirements.txt    # 依赖清单
├── config.yaml         # 默认配置
├── src/
│   ├── main.py         # CLI 入口
│   ├── sync.py         # 元数据同步
│   ├── asr.py          # B站音频下载 + Whisper 转录
│   ├── processor.py    # 处理编排
│   ├── llm.py          # LLM 文本清洗 + 摘要
│   ├── exporter.py     # Markdown 导出
│   ├── database.py     # SQLite 状态管理
│   ├── config.py       # 配置加载
│   ├── auth.py         # Cookie 验证
│   └── api/            # B站 API 模块
└── output/             # 生成的 Markdown
```
