# B站收藏夹/稍后再看 → 文字归档工具

抓取 B站账号的"收藏夹"和"稍后再看"里的全部视频，获取字幕文字内容，用 LLM 整理成"优化后原文"+"内容概括"，输出为 Obsidian 兼容的 Markdown 文件。

## 功能

- **阶段0**：同步收藏夹 + 稍后再看的全部视频元数据到本地 SQLite
- **阶段1**：下载视频官方字幕（优先 AI 字幕 → UP主上传字幕）
- **阶段3+4**：LLM 文本整理（加标点/分段/去口语词）+ 内容摘要
- **阶段5**：导出为 Obsidian 兼容 Markdown（含 YAML frontmatter）
- **增量运行**：已完成的不重复处理，支持随时中断续跑

## 安装

```bash
# 要求 Python >= 3.11
git clone <repo-url> bilibili-sync
cd bilibili-sync

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 安装
pip install -e .
```

## 配置

### 1. 获取 Cookie

1. 浏览器打开 [bilibili.com](https://www.bilibili.com) 并登录
2. F12 → Application → Cookies → 找到 `SESSDATA` 字段
3. 复制其值（URL 编码的长字符串）

### 2. 配置环境变量

```bash
# 复制模板
cp .env.example .env

# 编辑 .env 文件
BILIBILI_SESSDATA=你的SESSDATA值
LLM_API_KEY=你的LLM_API_KEY
LLM_BASE_URL=https://api.openai.com/v1   # 或其他 OpenAI 兼容接口
LLM_MODEL=gpt-4o-mini
```

也可以用 `config.yaml` 配置，环境变量优先级更高。

### 3. LLM 提供商

支持任何 OpenAI 兼容 API：

| 提供商 | base_url |
|---|---|
| OpenAI | `https://api.openai.com/v1` |
| DeepSeek | `https://api.deepseek.com/v1` |
| Groq | `https://api.groq.com/openai/v1` |
| Ollama (本地) | `http://localhost:11434/v1` |

## 使用

```bash
# 查看当前进度
bilibili-sync status

# 第一步：同步元数据
bilibili-sync sync

# 第二步：下载字幕 + LLM 处理
bilibili-sync process

# 第三步：导出 Markdown
bilibili-sync export

# 一键运行全部
bilibili-sync run

# 只同步指定的收藏夹
bilibili-sync sync --folders 123456789

# 只下载字幕，跳过 LLM（先收集数据）
bilibili-sync process --skip-llm

# 重试之前失败的视频
bilibili-sync process --retry-errors
```

## 输出结构

```
output/
├── 收藏夹/
│   ├── 默认收藏夹/
│   │   ├── 视频标题A.md
│   │   ├── 视频标题B.md
│   │   └── ...
│   └── 编程学习/
│       └── ...
└── 稍后再看/
    ├── 视频标题X.md
    └── ...
```

每个 `.md` 文件包含 YAML frontmatter 元数据、内容概括和完整文字记录，可直接导入 Obsidian。

## 状态机

```
pending → metadata_synced → subtitle_downloaded → llm_processed → markdown_generated
                        ↘ no_subtitle（无字幕，跳过）
                    任意步骤 → error（超过重试次数）
```

## 风控说明

- 接口间随机延时 1-3 秒（可配置）
- 全顺序执行，不做并发
- 请求失败自动重试（指数退避）
- 不保留任何视频/音频文件，只存文字

## 依赖

- Python >= 3.11
- requests, pyyaml, python-dotenv, openai
