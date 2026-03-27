import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path("complaints.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Таблица жалоб
    c.execute("""
    CREATE TABLE IF NOT EXISTS complaints(
        id TEXT PRIMARY KEY,
        user_id INTEGER,
        username TEXT,
        category TEXT,
        district TEXT,
        address_text TEXT,
        geo_lat REAL,
        geo_lon REAL,
        text TEXT,
        media_group_id TEXT,
        status TEXT,
        assignee_id INTEGER,
        created_at TEXT,
        taken_at TEXT,
        done_at TEXT,
        closed_at TEXT
    );
    """)

    # Таблица медиа
    c.execute("""
    CREATE TABLE IF NOT EXISTS media(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id TEXT,
        file_id TEXT,
        kind TEXT
    );
    """)

    # Таблица постов (карточка в группе ↔ message_id)
    c.execute("""
    CREATE TABLE IF NOT EXISTS posts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id TEXT,
        chat_id INTEGER,
        message_id INTEGER
    );
    """)

    # Таблица подсказок/хинтов (временные сообщения «Свободная заявка»)
    c.execute("""
    CREATE TABLE IF NOT EXISTS hints(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        complaint_id TEXT,
        message_id INTEGER
    );
    """)

    conn.commit()
    conn.close()


# -------------------------------
# Жалобы
# -------------------------------

def save_complaint(row: dict):
    """Сохранение жалобы. Принимает dict (как формирует handlers_user)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO complaints(
            id, user_id, username, category, district, address_text, geo_lat, geo_lon,
            text, media_group_id, status, assignee_id, created_at, taken_at, done_at, closed_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        row["id"],
        row["user_id"],
        row.get("username"),
        row.get("category"),
        row.get("district"),
        row.get("address_text"),
        row.get("geo_lat"),
        row.get("geo_lon"),
        row.get("text"),
        row.get("media_group_id"),
        row.get("status", "New"),
        row.get("assignee_id"),
        datetime.utcnow().isoformat(),
        None, None, None
    ))
    conn.commit()
    conn.close()

def add_media(cid: str, file_id: str, kind: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO media (complaint_id, file_id, kind) VALUES (?, ?, ?)", (cid, file_id, kind))
    conn.commit()
    conn.close()

def get_media(cid: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT file_id, kind FROM media WHERE complaint_id=?", (cid,))
    rows = c.fetchall()
    conn.close()
    return rows

def set_status(cid: str, status: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    if status == "InProgress":
        c.execute("UPDATE complaints SET status=?, taken_at=? WHERE id=?", (status, now, cid))
    elif status == "Done":
        c.execute("UPDATE complaints SET status=?, done_at=? WHERE id=?", (status, now, cid))
    elif status == "Closed":
        c.execute("UPDATE complaints SET status=?, closed_at=? WHERE id=?", (status, now, cid))
    else:
        c.execute("UPDATE complaints SET status=? WHERE id=?", (status, cid))
    conn.commit()
    conn.close()

def assign(cid: str, user_id: int | None):
    """Назначить/снять исполнителя.
    - Если user_id is None → снимаем исполнителя и taken_at.
    - Если задан → ставим исполнителя, проставляем taken_at и переводим в InProgress.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if user_id is None:
        c.execute("UPDATE complaints SET assignee_id=NULL, taken_at=NULL WHERE id=?", (cid,))
    else:
        c.execute("UPDATE complaints SET assignee_id=?, taken_at=?, status='InProgress' WHERE id=?",
                  (user_id, datetime.utcnow().isoformat(), cid))
    conn.commit()
    conn.close()

def get_complaint(cid: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM complaints WHERE id=?", (cid,))
    row = c.fetchone()
    conn.close()
    return row


# -------------------------------
# Посты (карточки в группе)
# -------------------------------

def save_post_message(cid: str, chat_id: int, msg_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO posts (complaint_id, chat_id, message_id) VALUES (?, ?, ?)", (cid, chat_id, msg_id))
    conn.commit()
    conn.close()

def get_post_message_id(cid: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT message_id FROM posts WHERE complaint_id=? ORDER BY id DESC LIMIT 1", (cid,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


# -------------------------------
# Хинты (временные подсказочные сообщения)
# -------------------------------

def save_hint_message(cid: str, msg_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO hints (complaint_id, message_id) VALUES (?, ?)", (cid, msg_id))
    conn.commit()
    conn.close()

def get_hint_message(cid: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT message_id FROM hints WHERE complaint_id=? ORDER BY id DESC LIMIT 1", (cid,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def delete_hint_message(cid: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM hints WHERE complaint_id=?", (cid,))
    conn.commit()
    conn.close()


# -------------------------------
# Выборки для команд
# -------------------------------

def list_user_complaints(user_id: int, limit: int = 10):
    """Ровно те поля, которые ждёт handlers_user.py"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, category, address_text, text, status, created_at, done_at
        FROM complaints
        WHERE user_id = ?
        ORDER BY datetime(created_at) DESC
        LIMIT ?
    """, (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows

def list_inprogress_detailed(limit: int = 20):
    """(id, category, address_text, text, assignee_id, taken_at)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, category, address_text, text, assignee_id, taken_at
        FROM complaints
        WHERE status = 'InProgress'
        ORDER BY datetime(taken_at) DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def list_done_detailed(limit: int = 20):
    """(id, category, address_text, text, assignee_id, done_at)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, category, address_text, text, assignee_id, done_at
        FROM complaints
        WHERE status = 'Done'
        ORDER BY datetime(done_at) DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

# --- свободные заявки: самые новые вверху
def list_free(limit: int = 10):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("""
        SELECT id, category, address_text, text, created_at
        FROM complaints
        WHERE status = 'New' AND (assignee_id IS NULL OR assignee_id = '')
        ORDER BY datetime(created_at) DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

# --- заявки, взятые конкретным исполнителем (активные)
def list_assignee_jobs(user_id: int, limit: int = 20, active_only: bool = True):
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    if active_only:
        c.execute("""
            SELECT id, category, address_text, text, status, taken_at
            FROM complaints
            WHERE assignee_id = ? AND status = 'InProgress'
            ORDER BY datetime(taken_at) DESC
            LIMIT ?
        """, (user_id, limit))
    else:
        c.execute("""
            SELECT id, category, address_text, text, status, taken_at
            FROM complaints
            WHERE assignee_id = ?
            ORDER BY datetime(taken_at) DESC
            LIMIT ?
        """, (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows


