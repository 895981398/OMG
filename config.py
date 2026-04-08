import os

# ====== MiniMax API（必需）======
# 启动前设置：export MINIMAX_KEY='your-key'
MINIMAX_KEY = os.environ.get('MINIMAX_KEY', '')

# ====== 微信数据库路径 ======
# 以下路径请根据实际修改，或通过环境变量覆盖
DECRYPTED_DIR = os.environ.get('DECRYPTED_DIR', './decrypted')
KEYS_FILE = os.environ.get('KEYS_FILE', './all_keys.json')

# 微信联系人数据库（从 DECRYPTED_DIR 推导）
CONTACT_DB = os.path.join(DECRYPTED_DIR, 'Contact', 'wccontact_new2.db')

# ====== 微信 WAL 路径 ======
# Mac 微信 3.8.10 固定路径，版本不同路径不同
# 通过 find_all_keys.py 提取密钥时自动获得
WAL_BASE = os.environ.get('WAL_BASE', '/Users/{username}/Library/Containers/com.tencent.xinWeChat/Data/Library/Application Support/com.tencent.xinWeChat/2.0b4.0.9/{hash}/Message')

# ====== 本机微信身份 ======
# 你的微信 wxid，登录 wx.xom 后查看 Web 版或数据库
MY_WXID = os.environ.get('MY_WXID', '')

# ====== 持久化文件 ======
DATA_DIR = os.environ.get('DATA_DIR', os.path.expanduser('~/.openclaw'))
os.makedirs(DATA_DIR, exist_ok=True)
PROCESSED_FILE = os.path.join(DATA_DIR, 'wechat_reply_processed.json')
CONTEXT_FILE = os.path.join(DATA_DIR, 'wechat_reply_context.json')

# 人格配置（项目内）
PERSONA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'personalities.json')
CURRENT_PERSONA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.current_persona')

# ====== 工具路径 ======
CLICLICK_BIN = '/usr/local/bin/cliclick'

# ====== 运行参数 ======
MERGE_WINDOW = 5        # 5秒内连续消息合并
WECHAT_CLOSE_DELAY = 60 # 无消息多少秒后隐藏微信窗口
WHITELIST = []          # 白名单（暂未使用）
