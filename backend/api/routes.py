import sqlite3
import json
from functools import wraps
from datetime import datetime
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from flask_jwt_extended import jwt_required

from backend.database.filter_db import save_filtered_data
from backend.database.database import (
    DB_PATH,
    init_db,
    create_app_tables
)
from backend.api.google_sync import (
    sync_group_to_calendar,
    sync_events_in_date_range,
    get_calendar_service,
    CALENDAR_ID,
    parse_date_str,
    ensure_google_event_id_column
)

import os
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../frontend'))
app = Flask(
    __name__,
    static_folder=FRONTEND_DIR,
    static_url_path=''
)

CORS(app)

ACADEMIC_WEEK_OFFSET = 6


def extract_week_from_date_str(date_str: str) -> int:
    """
    Parse a string like "Пн, 26 мая" into a date and return academic week number.
    """
    dt = parse_date_str(date_str)
    iso_week = dt.isocalendar()[1]
    return iso_week - ACADEMIC_WEEK_OFFSET


# ——— Initialize database and tables ———
conn = sqlite3.connect(DB_PATH, timeout=5)
init_db(conn)
create_app_tables(conn)
ensure_google_event_id_column()
conn.close()


# ——— Database utilities ———
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def query_db(query: str, args=(), one: bool = False):
    conn = get_db_connection()
    cur = conn.execute(query, args)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows[0] if one and rows else rows


def execute_db(query: str, args=()):
    conn = sqlite3.connect(DB_PATH, timeout=5)
    cur = conn.cursor()
    cur.execute(query, args)
    conn.commit()
    last_id = cur.lastrowid
    cur.close()
    conn.close()
    return last_id


# ——— Simple JWT authentication with JSON token ———
def jwt_required():
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                return jsonify({"msg": "Missing Authorization Header"}), 401
            token = auth.split(" ", 1)[1]
            try:
                identity = json.loads(token)
            except Exception:
                return jsonify({"msg": "Invalid token"}), 401
            g.current_user = identity
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def get_jwt_identity():
    return getattr(g, "current_user", None)


@app.route('/')
def serve_index():
    return app.send_static_file('index.html')


# ——— User registration and login ———
@app.route("/register", methods=["POST"])
def register_user():
    data = request.get_json(force=True)
    try:
        execute_db(
            "INSERT INTO users (email, password, role) VALUES (?, ?, ?)",
            (data["email"], data["password"], data.get("role", "student"))
        )
    except sqlite3.IntegrityError:
        return jsonify({"msg": "Пользователь с таким email уже существует"}), 409
    return jsonify({"msg": "Пользователь зарегистрирован"}), 201


@app.route("/login", methods=["POST"])
def login_user():
    data = request.get_json(force=True)
    row = query_db(
        "SELECT id, password, role FROM users WHERE email = ?",
        (data["email"],), one=True
    )
    if not row or row["password"] != data["password"]:
        return jsonify({"msg": "Неверный логин или пароль"}), 401
    token = json.dumps({"user_id": row["id"], "role": row["role"]})
    return jsonify(access_token=token, is_admin=(row["role"] == "admin")), 200


# ——— User management endpoints ———
@app.route("/users/<int:user_id>/promote", methods=["POST"])
@jwt_required()
def promote_user(user_id):
    user = get_jwt_identity()
    if user["role"] != "admin":
        return jsonify({"msg": "Недостаточно прав"}), 403
    execute_db("UPDATE users SET role = 'admin' WHERE id = ?", (user_id,))
    return jsonify({"msg": f"Пользователь #{user_id} назначен админом"}), 200


@app.route("/users/<int:user_id>/demote", methods=["POST"])
@jwt_required()
def demote_user(user_id):
    user = get_jwt_identity()
    if user["role"] != "admin":
        return jsonify({"msg": "Недостаточно прав"}), 403
    target = query_db("SELECT role FROM users WHERE id = ?", (user_id,), one=True)
    if not target or target["role"] != "admin":
        return jsonify({"msg": "Пользователь не админ"}), 400
    execute_db("UPDATE users SET role = 'user' WHERE id = ?", (user_id,))
    return jsonify({"msg": f"Пользователь #{user_id} лишен прав администратора"}), 200


@app.route("/users", methods=["GET"])
@jwt_required()
def get_users():
    user = get_jwt_identity()
    if user["role"] != "admin":
        return jsonify({"msg": "Недостаточно прав"}), 403
    rows = query_db("SELECT id, email, role FROM users")
    return jsonify([dict(r) for r in rows]), 200


# ——— Groups endpoint ———
@app.route("/groups", methods=["GET"])
def get_groups():
    rows = query_db("SELECT name FROM groups")
    return jsonify([r["name"] for r in rows]), 200


# ——— Schedule endpoints ———
@app.route("/schedule", methods=["GET"])
def get_schedule():
    group = request.args.get("group")
    week = request.args.get("week")
    if not group or not week:
        return jsonify({"error": "Параметры group и week обязательны"}), 400
    rows = query_db(
        """
        SELECT s.id, s.date AS date, s.time AS time,
               s.subject, s.teachers, s.rooms, s.is_custom
        FROM schedule s
        JOIN groups g ON s.group_id = g.id
        WHERE g.name = ? AND s.week = ?
        """,
        (group, week)
    )
    result = []
    for r in rows:
        try:
            teachers = json.loads(r["teachers"])
        except:
            teachers = []
        try:
            rooms = json.loads(r["rooms"])
        except:
            rooms = []
        result.append({
            "id": r["id"],
            "date": r["date"],
            "time": r["time"],
            "subject": r["subject"],
            "teachers": teachers,
            "rooms": rooms,
            "is_custom": bool(r["is_custom"])
        })
    return jsonify(result), 200


@app.route("/schedule/<int:item_id>", methods=["DELETE"])
@jwt_required()
def delete_schedule(item_id):
    user = get_jwt_identity()
    if user["role"] != "admin":
        return jsonify({"msg": "Удаление доступно только админам"}), 403
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT is_custom FROM schedule WHERE id = ?", (item_id,))
    sch = cur.fetchone()
    if not sch:
        conn.close()
        return jsonify({"msg": "Пара не найдена"}), 404
    if sch["is_custom"]:
        cur.execute(
            "SELECT google_event_id FROM occupied_rooms WHERE schedule_id = ?",
            (item_id,)
        )
        row = cur.fetchone()
        if row and row["google_event_id"]:
            try:
                service = get_calendar_service()
                service.events().delete(
                    calendarId=CALENDAR_ID,
                    eventId=row["google_event_id"]
                ).execute()
            except Exception as e:
                print(f"[GOOGLE_SYNC] Не удалось удалить событие {row['google_event_id']}: {e}")
    cur.execute("DELETE FROM schedule WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    save_filtered_data()
    return jsonify({"msg": "Пара удалена и календарь обновлён"}), 200


@app.route("/schedule/<int:item_id>", methods=["PUT"])
@jwt_required()
def update_schedule(item_id):
    user = get_jwt_identity()
    if user["role"] not in ("teacher", "admin"):
        return jsonify({"msg": "Недостаточно прав"}), 403
    data = request.get_json(force=True)
    week = extract_week_from_date_str(data["date"])
    execute_db(
        """
        UPDATE schedule
           SET week=?, date=?, time=?, subject=?, teachers=?, rooms=?, is_custom=1
         WHERE id=?
        """,
        (
            week,
            data["date"],
            data["time"],
            data["subject"],
            json.dumps(data["teachers"]),
            json.dumps(data["rooms"]),
            item_id
        )
    )
    save_filtered_data()
    sync_group_to_calendar(data["group_name"])
    return jsonify({"msg": "Обновлено"}), 200


@app.route("/schedule", methods=["POST"])
@jwt_required()
def add_schedule():
    user = get_jwt_identity()
    if user["role"] not in ("teacher", "admin"):
        return jsonify({"msg": "Недостаточно прав"}), 403
    data = request.get_json(force=True)
    grp = query_db(
        "SELECT id FROM groups WHERE name = ?",
        (data["group_name"],), one=True
    )
    if not grp:
        return jsonify({"error": "Группа не найдена"}), 404
    week = extract_week_from_date_str(data["date"])
    execute_db(
        """
        INSERT INTO schedule
            (group_id, week, date, time, subject, teachers, rooms, is_custom)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """, (
            grp["id"],
            week,
            data["date"],
            data["time"],
            data["subject"],
            json.dumps(data["teachers"]),
            json.dumps(data["rooms"])
        )
    )
    save_filtered_data()
    sync_group_to_calendar(data["group_name"])
    return jsonify({"msg": "Занятие добавлено"}), 201


# ——— Room availability endpoints ———
@app.route("/occupied_rooms", methods=["GET"])
def occupied_rooms():
    rows = query_db(
        "SELECT schedule_id AS id, week, day, start_time, end_time, room, subject, teacher, group_name FROM occupied_rooms"
    )
    return jsonify([
        {
            "id": r["id"],
            "week": r["week"],
            "day": r["day"],
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "room": r["room"],
            "subject": r["subject"],
            "teacher": r["teacher"],
            "group_name": r["group_name"]
        } for r in rows
    ]), 200


@app.route("/free_rooms", methods=["GET"])
def free_rooms():
    rows = query_db(
        "SELECT week, day, start_time, end_time, room FROM free_rooms"
    )
    return jsonify([
        {
            "week": r["week"],
            "day": r["day"],
            "start_time": r["start_time"],
            "end_time": r["end_time"],
            "room": r["room"]
        } for r in rows
    ]), 200


# ——— Google Calendar synchronization endpoints ———
@app.route("/calendar/sync_group", methods=["POST"])
@jwt_required()
def sync_group_calendar():
    data = request.get_json(force=True)
    group = data.get("group")
    if not group:
        return jsonify({"error": "Укажите группу"}), 400
    sync_group_to_calendar(group)
    return jsonify({"msg": f"Расписание группы {group} добавлено в Google Calendar"}), 200


@app.route("/calendar/sync_range", methods=["POST"])
def sync_range_calendar():
    data = request.get_json(force=True)
    start = data.get("start_date")
    end = data.get("end_date")
    if not start or not end:
        return jsonify({"error": "Введите start_date и end_date"}), 400
    try:
        sd = datetime.strptime(start, "%d.%m.%Y").date()
        ed = datetime.strptime(end, "%d.%m.%Y").date()
    except ValueError as e:
        return jsonify({"error": f"Неверный формат даты: {e}"}), 400
    if ed < sd:
        return jsonify({"error": "Дата окончания раньше даты начала"}), 400
    sync_events_in_date_range(sd, ed)
    return jsonify({"msg": f"Синхронизированы события с {sd} по {ed}"}), 200


# ——— Allowed rooms endpoint ———
@app.route("/allowed_rooms", methods=["GET"])
def allowed_rooms():
    from backend.database.filter_db import ALLOWED_IT_ROOMS
    return jsonify(sorted(ALLOWED_IT_ROOMS)), 200


if __name__ == "__main__":
    # host='0.0.0.0' позволяет принимать запросы с любого IP
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
