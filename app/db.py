import os
import sqlite3
import hashlib
import secrets
from typing import Optional, Dict, Any, List

DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
DB_PATH = os.path.join(DATA_DIR, "devices.db")


def get_db_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    device_id TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    device_name TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
    finally:
        conn.close()


def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    if not salt:
        salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100000
    ).hex()
    return pw_hash, salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    calc_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(calc_hash, expected_hash)


def create_or_update_device(name: str, device_id: str, client_id: str, password: str) -> Dict[str, Any]:
    init_db()
    pw_hash, salt = hash_password(password)
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
                INSERT INTO devices (name, device_id, client_id, password_hash, salt)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    device_id=excluded.device_id,
                    client_id=excluded.client_id,
                    password_hash=excluded.password_hash,
                    salt=excluded.salt;
            """, (name.strip(), device_id.strip(), client_id.strip(), pw_hash, salt))
        return {
            "name": name.strip(),
            "device_id": device_id.strip(),
            "client_id": client_id.strip(),
        }
    finally:
        conn.close()


def get_device_by_name(name: str) -> Optional[Dict[str, Any]]:
    init_db()
    conn = get_db_connection()
    try:
        cur = conn.execute("SELECT * FROM devices WHERE name = ?", (name.strip(),))
        row = cur.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def get_device_by_device_id(device_id: str) -> Optional[Dict[str, Any]]:
    init_db()
    conn = get_db_connection()
    try:
        cur = conn.execute("SELECT * FROM devices WHERE device_id = ? ORDER BY id DESC LIMIT 1", (device_id.strip(),))
        row = cur.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def list_devices() -> List[Dict[str, Any]]:
    init_db()
    conn = get_db_connection()
    try:
        cur = conn.execute("SELECT id, name, device_id, client_id, created_at FROM devices ORDER BY id ASC")
        return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def authenticate_device(name: str, password: str) -> Optional[Dict[str, Any]]:
    dev = get_device_by_name(name)
    if not dev:
        return None
    if verify_password(password, dev["salt"], dev["password_hash"]):
        return {
            "name": dev["name"],
            "device_id": dev["device_id"],
            "client_id": dev["client_id"],
        }
    return None


def create_session(device_name: str) -> str:
    init_db()
    token = secrets.token_urlsafe(32)
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("INSERT INTO sessions (token, device_name) VALUES (?, ?)", (token, device_name.strip()))
        return token
    finally:
        conn.close()


def verify_session(token: str) -> Optional[str]:
    init_db()
    conn = get_db_connection()
    try:
        cur = conn.execute("SELECT device_name FROM sessions WHERE token = ?", (token,))
        row = cur.fetchone()
        if row:
            return row["device_name"]
        return None
    finally:
        conn.close()


def delete_session(token: str):
    init_db()
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    finally:
        conn.close()
