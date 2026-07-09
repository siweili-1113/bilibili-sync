# ASR 环境记录

## 安装方式

### 方式一：一键安装（推荐）

```bash
./setup.sh
```

### 方式二：手动安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e "." -i https://pypi.tuna.tsinghua.edu.cn/simple
cp .env.example .env
nano .env
```

## 依赖包（通过清华镜像安装）

| 包 | 版本 | 用途 |
|---|---|---|
| faster-whisper | 1.x | 本地语音转文字（CTranslate2 加速） |
| ctranslate2 | 4.x | faster-whisper 推理引擎（无需 torch） |
| openai | 2.x | LLM API 调用 |
| requests | 2.x | HTTP 请求 |
| pyyaml | 6.x | 配置文件解析 |
| python-dotenv | 1.x | 环境变量加载 |

## 下载的模型

- **Whisper small** (~500MB) → `~/.cache/huggingface.co/hub/models--Systran--faster-whisper-small/`
- 首次运行 ASR 时自动下载，使用 `HF_ENDPOINT=https://hf-mirror.com` 镜像
- 禁用 Xet 协议（`HF_HUB_DISABLE_XET=1`），强制 HTTP 下载

## HuggingFace 镜像配置

```bash
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_ENABLE_HF_TRANSFER=0   # 禁用 Xet 加速（镜像不支持）
export HF_HUB_DISABLE_XET=1          # 强制使用 HTTP 下载
```

## 清理

```bash
./cleanup.sh
```

卸载 faster-whisper 及相关包、删除 Whisper 模型、清理临时音频。
