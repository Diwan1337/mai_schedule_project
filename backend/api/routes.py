import sqlite3
import json
from functools import wraps
from datetime import datetime
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from backend.database.filter_db import save_filtered_data
from backend.database.database import (
    DB_PATH,
    init_db,  # создаёт parser_pairs + groups
    create_app_tables  # создаёт users, schedule, occupied_rooms, free_rooms, changes_log
)
from backend.api.google_sync import (
    sync_group_to_calendar,
    sync_events_in_date_range
)

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# ——— Инициализация БД ———
# 1) парсер-таблицы (init_db)
# 2) таблицы приложения (create_app_tables)
conn = sqlite3.connect(DB_PATH, timeout=5)
init_db(conn)
create_app_tables(conn)
conn.close()


# ——— Утилиты для работы с БД ———
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


# ——— Простейшая «JWT» авторизация с JSON-токеном ——— #
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


# ——— Регистрация и логин ——— #
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

    # mister kostil
    return jsonify(access_token=token, is_admin=(row["role"] == "admin")), 200


@app.route("/users/<int:user_id>/promote", methods=["POST"])
@jwt_required()
def promote_user(user_id):
    user = get_jwt_identity()
    if user["role"] != "admin":
        return jsonify({"msg": "Недостаточно прав"}), 403

    execute_db("UPDATE users SET role = 'admin' WHERE id = ?", (user_id,))
    return jsonify({"msg": f"Пользователь #{user_id} назначен админом"}), 200

@app.route("/users", methods=["GET"])
@jwt_required()
def get_users():
    user = get_jwt_identity()
    if user["role"] != "admin":
        return jsonify({"msg": "Недостаточно прав"}), 403

    rows = query_db("SELECT id, email, role FROM users")
    return jsonify([dict(r) for r in rows]), 200


# ——— Группы ——— #
@app.route("/groups", methods=["GET"])
def get_groups():
    rows = query_db("SELECT name FROM groups")
    return jsonify([r["name"] for r in rows]), 200


# ——— Расписание ——— #
@app.route("/schedule", methods=["GET"])
def get_schedule():
    group = request.args.get("group")
    week = request.args.get("week")
    if not group or not week:
        return jsonify({"error": "Параметры group и week обязательны"}), 400

    rows = query_db(
        """
        SELECT s.id,
            s.date    AS date,
            s.time    AS time,
            s.subject,
            s.teachers,
            s.rooms,
            s.is_custom
        FROM schedule s
        JOIN groups  g ON s.group_id = g.id
        WHERE g.name = ? AND s.week = ?
        """,
        (group, week)
    )
    result = []

    for r in rows:
        # teachers и rooms хранятся как JSON-строки
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

    # Удалим по ID
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM schedule WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()

    # После удаления — пересчёт комнат
    save_filtered_data()

    return jsonify({"msg": f"Пара с ID={item_id} удалена"}), 200


@app.route("/schedule", methods=["POST"])
@jwt_required()
def add_schedule():
    user = get_jwt_identity()
    if user["role"] not in ("teacher", "admin"):
        return jsonify({"msg": "Недостаточно прав"}), 403

    data = request.get_json(force=True)

    # Находим ID группы
    grp = query_db("SELECT id FROM groups WHERE name = ?", (data["group_name"],), one=True)
    if not grp:
        return jsonify({"error": "Группа не найдена"}), 404
    group_id = grp["id"]

    # Собираем JSON-поля
    teachers_json = json.dumps(data.get("teachers", []))
    rooms_json = json.dumps(data.get("rooms", []))

    execute_db(
        """
        INSERT INTO schedule
            (group_id, week, date, time, subject, teachers, rooms, is_custom)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            group_id,
            data["week"],
            data["date"],
            data["time"],
            data["subject"],
            teachers_json,
            rooms_json
        )
    )
    save_filtered_data()

    return jsonify({"msg": "Занятие добавлено"}), 201

# ——— Аудитории ——— #
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
            "group_name": r["group_name"],
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
            "room": r["room"],
        } for r in rows
    ]), 200


# ——— Синхронизация с Google ——— #
@app.route("/calendar/sync_group", methods=["POST"])
@jwt_required()
def sync_group_calendar():
    data = request.get_json(force=True)
    if not data.get("group"):
        return jsonify({"error": "Укажите группу"}), 400
    sync_group_to_calendar(data["group"])
    return jsonify({"msg": f"Расписание группы {data['group']} добавлено в Google Calendar"}), 200


@app.route("/calendar/sync_range", methods=["POST"])
def sync_range_calendar():
    data = request.get_json(force=True)
    sd = data.get("start_date")
    ed = data.get("end_date")
    if not sd or not ed:
        return jsonify({"error": "Введите start_date и end_date"}), 400
    try:
        sd_dt = datetime.strptime(sd, "%d.%m.%Y").date()
        ed_dt = datetime.strptime(ed, "%d.%m.%Y").date()
    except ValueError as e:
        return jsonify({"error": f"Неверный формат даты: {e}"}), 400
    if ed_dt < sd_dt:
        return jsonify({"error": "Дата окончания раньше даты начала"}), 400
    sync_events_in_date_range(sd_dt, ed_dt)
    return jsonify({"msg": f"Синхронизированы события с {sd_dt} по {ed_dt}"}), 200

@app.route("/allowed_rooms", methods=["GET"])
def allowed_rooms():
    from backend.database.filter_db import ALLOWED_IT_ROOMS
    return jsonify(sorted(ALLOWED_IT_ROOMS)), 200


if __name__ == "__main__":
    # Чтобы SQLite не блокироваться
    app.run(debug=False, use_reloader=False, port=5000)
