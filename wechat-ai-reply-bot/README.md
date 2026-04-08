# 微信 AI 自动回复机器人

基于 OpenClaw 的微信自动回复机器人，支持多 AI 模型自动切换、消息合并、上下文记忆。

## 功能特性

- 🤖 **多 AI 模型切换**：Doubao + MiniMax 自动切换
- 💬 **消息合并**：5秒内多消息合并回复
- 🧠 **上下文记忆**：记住最近对话
- 🎭 **人格切换**：支持多种聊天人格
- 🔒 **并发控制**：工业级并发架构，防重复、防卡死
- ✨ **真人化处理**：去除 AI 感
- 🔐 **微信数据库解密**：内置解密工具

## 解密工具来源

本项目中的 `tools/` 目录下的微信解密工具来源于本人开源项目：

**https://github.com/895981398/OMG**

> 原始项目 wechat-decrypt-mac 是用于从微信进程内存中提取密钥并解密 macOS 微信数据库的工具。

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/895981398/OMG.git
cd wechat-ai-reply-bot
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
# AI 模型密钥
export DOUBO_KEY='your-doubao-api-key'
export MINIMAX_KEY='your-minimax-api-key'

# 微信路径配置（根据实际修改）
export WAL_BASE='/Users/xxx/Library/Containers/com.tencent.xinWeChat/Data/Library/Application Support/com.tencent.xinWeChat/2.0b4.0.9/xxxx/Message'
```

### 4. 提取微信密钥（需要微信在运行 + sudo）

```bash
cd tools
sudo python3 find_all_keys.py
# 成功后会生成 all_keys.json
cd ..
```

**前提条件：**
- macOS 系统
- 微信已在运行
- 关闭 SIP（系统完整性保护）

### 5. 解密数据库

```bash
cd tools
python3 decrypt_db.py
cd ..
```

### 6. 启动机器人

```bash
python3 main.py
```

## 项目结构

```
wechat-ai-reply-bot/
├── tools/                    # 微信解密工具
│   ├── config.py            # 解密工具配置
│   ├── crypto_params.py     # 加解密参数
│   ├── decrypt_db.py        # 数据库解密
│   └── find_all_keys.py    # 密钥提取
│
├── core.py                   # 核心逻辑
├── main.py                  # 入口
├── config.py               # 机器人配置
├── personalities.json       # 人格配置
├── all_keys.json           # ⚠️ 你的微信密钥（不同用户不同，不上传）
├── config.json             # ⚠️ 你的配置（不上传）
├── decrypted/              # ⚠️ 解密后数据（不上传）
├── requirements.txt
└── README.md
```

## ⚠️ 重要：私密文件

以下文件包含用户敏感信息，**不要上传或分享**：

- `all_keys.json` — 你的微信密钥
- `config.json` — 你的微信配置
- `decrypted/` — 解密后的数据库

这些文件已在 `.gitignore` 中排除。

## 配置说明

### 机器人配置（config.py）

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `MERGE_WINDOW` | 5 | 合并窗口（秒） |
| `MAX_MERGE_MESSAGES` | 3 | 最多合并消息条数 |
| `COOLDOWN` | 60 | 冷却时间（秒） |
| `MSG_SEPARATOR` | \|\|\|\| | 多条消息分隔符 |

### AI 参数

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

## License

MIT
