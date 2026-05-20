"""
用户账号管理模块
支持登录验证和注册
"""
import os
import json
import hashlib

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")


def _hash_password(password: str) -> str:
    """密码哈希"""
    return hashlib.sha256(password.encode()).hexdigest()


def _load_users() -> dict:
    """加载用户数据"""
    if not os.path.exists(USERS_FILE):
        os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
        # 创建默认管理员账号
        default_users = {
            "chenyin": {
                "password": _hash_password("wbxhn16.."),
                "role": "admin"
            }
        }
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_users, f, ensure_ascii=False, indent=2)
        return default_users
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_users(users: dict):
    """保存用户数据"""
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def verify_user(username: str, password: str) -> bool:
    """验证用户登录"""
    users = _load_users()
    if username not in users:
        return False
    return users[username]["password"] == _hash_password(password)


def register_user(username: str, password: str) -> tuple:
    """注册新用户，返回 (成功与否, 消息)"""
    if not username.strip() or not password.strip():
        return False, "用户名和密码不能为空"
    if len(username) < 2:
        return False, "用户名至少2个字符"
    if len(password) < 4:
        return False, "密码至少4个字符"

    users = _load_users()
    if username in users:
        return False, "用户名已存在"

    users[username] = {
        "password": _hash_password(password),
        "role": "user"
    }
    _save_users(users)
    return True, "注册成功！请登录"