import os

# ====== AI 模型配置 ======
# 支持多模型自动切换，按 priority 顺序尝试
# priority 数字越小越优先
# 启动前设置环境变量：
#   export DOUBO_KEY='your-doubao-api-key'
#   export MINIMAX_KEY='your-minimax-api-key'

MODELS = [
    {
        'name': 'doubao',
        'priority': 1,
        'endpoint': 'https://ark.cn-beijing.volces.com/api/v3/chat/completions',
        'model': 'doubao-seed-2-0-lite-260215',
        'api_key': os.environ.get('DOUBO_KEY', ''),
        'timeout': 20,
    },
    {
        'name': 'minimax',
        'priority': 2,
        'endpoint': 'https://api.minimax.chat/v1/text/chatcompletion_v2',
        'model': 'MiniMax-M2.7',
        'api_key': os.environ.get('MINIMAX_KEY', ''),
        'timeout': 15,
    },
]

# ====== AI API 通用参数 ======
API_PARAMS = {
    'temperature': 0.7,
    'top_p': 0.9,
    'frequency_penalty': 0.5,
    'presence_penalty': 0.1,
    'max_tokens': 64,
}

# ====== 并发控制 ======
MERGE_WINDOW = 5         # 合并窗口（秒）
MAX_MERGE_MESSAGES = 3  # 最多合并消息条数
COOLDOWN = 60            # 冷却时间（秒）
MSG_SEPARATOR = '||||'   # 多条消息分隔符

# 微信数据库路径（需根据实际修改）
DECRYPTED_DIR = os.environ.get('DECRYPTED_DIR', '/Users/zhang/Downloads/wechat-decrypt-mac/decrypted')
KEYS_FILE = os.environ.get('KEYS_FILE', '/Users/zhang/Downloads/wechat-decrypt-mac/all_keys.json')
CONTACT_DB = os.path.join(DECRYPTED_DIR, 'Contact', 'wccontact_new2.db')

# 微信 WAL 路径（Mac微信 3.8.10固定路径，版本不同路径不同）
WAL_BASE = os.environ.get('WAL_BASE', '/Users/zhang/Library/Containers/com.tencent.xinWeChat/Data/Library/Application Support/com.tencent.xinWeChat/2.0b4.0.9/d3180fae2b816038d1fad5b4ac0889a9/Message')

# 本机微信身份
MY_WXID = os.environ.get('MY_WXID', '')

# 持久化文件
DATA_DIR = os.environ.get('DATA_DIR', os.path.expanduser('~/.openclaw'))
os.makedirs(DATA_DIR, exist_ok=True)
PROCESSED_FILE = os.path.join(DATA_DIR, 'wechat_reply_processed.json')
CONTEXT_FILE = os.path.join(DATA_DIR, 'wechat_reply_context.json')

# 人格配置（项目内，不上传）
PERSONA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'personalities.json')
CURRENT_PERSONA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.current_persona')

# 工具路径
CLICLICK_BIN = '/usr/local/bin/cliclick'

# 运行参数
WECHAT_CLOSE_DELAY = 60
WHITELIST = []
