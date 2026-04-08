# 微信 AI 自动回复机器人

基于 OpenClaw 的微信自动回复机器人，支持多 AI 模型自动切换、消息合并、上下文记忆。

## 功能特性

- 🤖 **多 AI 模型切换**：Doubao + MiniMax 自动切换
- 💬 **消息合并**：5秒内多消息合并回复
- 🧠 **上下文记忆**：记住最近对话
- 🎭 **人格切换**：支持多种聊天人格
- 🔒 **并发控制**：工业级并发架构，防重复、防卡死
- ✨ **真人化处理**：去除 AI 感

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
export DOUBO_KEY='your-doubao-api-key'
export MINIMAX_KEY='your-minimax-api-key'
export MY_WXID='your-wechat-id'
export DECRYPTED_DIR='/path/to/decrypted-wechat-dir'
export KEYS_FILE='/path/to/all_keys.json'
```

### 3. 启动

```bash
python3 main.py
```

## 配置说明

所有配置项在 `config.py` 中：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `MERGE_WINDOW` | 5 | 合并窗口（秒） |
| `MAX_MERGE_MESSAGES` | 3 | 最多合并消息条数 |
| `COOLDOWN` | 60 | 冷却时间（秒） |
| `MSG_SEPARATOR` | \|\|\|\| | 多条消息分隔符 |

## AI 参数

| 参数 | 值 | 说明 |
|------|-----|------|
| temperature | 0.7 | 随性度 |
| top_p | 0.9 | - |
| frequency_penalty | 0.5 | 防重复 |
| presence_penalty | 0.1 | - |
| max_tokens | 64 | 强制短回复 |

## 命令

- `!人格` - 查看当前人格
- `!人格 <名字>` - 切换人格

## 架构

```
消息进来 → msg_queue → process_messages → user_messages(合并)
                                                    ↓
check_pending_messages → _do_ai_reply_safe → reply_queue → send_replies → 微信
```

## 注意事项

- `personalities.json` 包含人格配置，需根据实际修改
- API Key 通过环境变量设置，不写入代码
- 微信数据库解密需使用 wechat-decrypt-mac 工具
