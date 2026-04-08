"""
微信解密工具配置（环境变量方式）
解密工具来源：https://github.com/895981398/OMG
"""
import os

# 微信 WAL 路径（Mac微信 3.8.10，版本不同路径不同）
# 可通过环境变量 WECHAT_VERSION 指定版本
WECHAT_VERSION = os.environ.get('WECHAT_VERSION', '3.8.10')
WAL_BASE = os.environ.get('WAL_BASE', '/Users/zhang/Library/Containers/com.tencent.xinWeChat/Data/Library/Application Support/com.tencent.xinWeChat/2.0b4.0.9/d3180fae2b816038d1fad5b4ac0889a9/Message')

# 解密后数据库输出目录
DECRYPTED_DIR = os.environ.get('DECRYPTED_DIR', '/Users/zhang/Downloads/wechat-decrypt-mac/decrypted')

# 密钥文件路径
KEYS_FILE = os.environ.get('KEYS_FILE', '/Users/zhang/Downloads/wechat-decrypt-mac/all_keys.json')

def load_config():
    return {
        "db_dir": WAL_BASE,
        "decrypted_dir": DECRYPTED_DIR,
        "keys_file": KEYS_FILE
    }
