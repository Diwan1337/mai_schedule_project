import sqlite3
import json
import re
from backend.database.database import DB_PATH

ALLOWED_IT_ROOMS = {
    "ГУК Б-416", "ГУК Б-362", "ГУК Б-434", "ГУК Б-436", "ГУК Б-422",
    "ГУК Б-438", "ГУК Б-440", "ГУК Б-417", "ГУК Б-426", "ГУК Б-415",
    "ГУК Б-324", "ГУК Б-325", "ГУК Б-326", "ГУК Б-418", "ГУК Б-420"
}


def setup_db(conn: sqlite3.Connection):
    """Создаёт (пересоздаёт) occupied_rooms и free_rooms."""
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS free_rooms;")

    # Таблица occupied_rooms создаётся один раз (при первом запуске) и больше не сбрасывается,
    # чтобы в ней сохранялся google_event_id.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS occupied_rooms (
            schedule_id     INTEGER PRIMARY KEY,
            week            INTEGER,
            day             TEXT,
            start_time      TEXT,
            end_time        TEXT,
            room            TEXT,
            subject         TEXT,
            teacher         TEXT,
            group_name      TEXT,
            weekday         TEXT,
            google_event_id TEXT
        );
    """)

    # Схема для free_rooms
    cur.execute("""
        CREATE TABLE free_rooms (
            week       INTEGER,
            day        TEXT,
            start_time TEXT,
            end_time   TEXT,
            room       TEXT,
            PRIMARY KEY (week, day, start_time, end_time, room)
        );
    """)

    conn.commit()


def get_occupied_rooms(conn: sqlite3.Connection):
    """
    Из парсерной таблицы schedule с JOIN по groups берёт все уроки,
    парсит JSON-поля, фильтрует по ALLOWED_IT_ROOMS и возвращает
    список кортежей
    (week, date, start_time, end_time, room, subject, teacher, group_name, weekday).
    """
    cur = conn.cursor()
    cur.execute("""
    SELECT s.id,
           s.week,
           s.date,
           s.time,
           s.subject,
           s.teachers,
           s.rooms,
           g.name AS group_name
    FROM schedule s
    JOIN groups  g ON s.group_id = g.id
    """)

    rows = cur.fetchall()
    print(f"[FILTER_DB] Прочитано строк из schedule: {len(rows)}")

    occupied = []
    for schedule_id, week, date_str, time_str, subject, teachers_json, rooms_json, group_name in rows:
        # преподаватели
        try:
            teachers = json.loads(teachers_json)
        except:
            teachers = []
        teacher = ", ".join(teachers)

        clean_time = re.sub(r"[–—]", "-", time_str)
        parts = [p.strip() for p in clean_time.split("-")]
        if len(parts) != 2:
            continue
        start_time, end_time = parts

        # аудитории
        try:
            rooms = json.loads(rooms_json)
        except:
            rooms = []

        # день недели (до запятой)
        weekday = date_str.split(",", 1)[0].strip()

        # оставляем только нужные аудитории
        for room in rooms:
            if room in ALLOWED_IT_ROOMS:
                occupied.append((
                    schedule_id,
                    week,
                    date_str,
                    start_time,
                    end_time,
                    room,
                    subject,
                    teacher,
                    group_name,
                    weekday
                ))

    print(f"[FILTER_DB] Сгенерировано occupied-записей: {len(occupied)}")
    return occupied


def get_free_rooms(occupied):
    """
    На основе списка occupied генерирует все свободные слоты
    по тем же неделям/дням/временным слотам и по тем же кабинетам.
    """
    weeks = sorted({rec[0] for rec in occupied})
    days = sorted({rec[1] for rec in occupied})
    slots = sorted({(rec[2], rec[3]) for rec in occupied})
    rooms_all = sorted({rec[4] for rec in occupied})
    occupied_set = {(w, d, s, e, r) for w, d, s, e, r, *_ in occupied}

    free = []
    for w in weeks:
        for d in days:
            for s, e in slots:
                for r in rooms_all:
                    key = (w, d, s, e, r)
                    if key not in occupied_set:
                        free.append(key)
    print(f"[FILTER_DB] Сгенерировано free-записей: {len(free)}")
    return free


def save_filtered_data():
    """
    Пересоздаёт free_rooms и обновляет occupied_rooms, сохраняя google_event_id.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1) удаляем из occupied те пары, которых уже нет в schedule (is_custom=1)
    cur.execute("""
        DELETE FROM occupied_rooms
        WHERE schedule_id NOT IN (
            SELECT id FROM schedule WHERE is_custom = 1
        )
    """)

    # 2) сбрасываем free_rooms
    cur.execute("DROP TABLE IF EXISTS free_rooms;")
    cur.execute("""
        CREATE TABLE free_rooms (
            week       INTEGER,
            day        TEXT,
            start_time TEXT,
            end_time   TEXT,
            room       TEXT,
            PRIMARY KEY (week, day, start_time, end_time, room)
        );
    """)

    # 3) собираем новые occupied (но не дропаем occupied_rooms — чтобы не слетали google_event_id)
    occupied = get_occupied_rooms(conn)
    unique = {}
    for rec in occupied:
        key = rec[:5]
        if key not in unique:
            unique[key] = rec
    occ_list = list(unique.values())

    # 4) вставляем новые занятые (INSERT OR IGNORE не трогает уже существующие строки с google_event_id)
    cur.executemany(
        "INSERT OR IGNORE INTO occupied_rooms "
        "(schedule_id, week, day, start_time, end_time, room, subject, teacher, group_name, weekday) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
        occ_list
    )

    # 5) генерируем и вставляем новые свободные
    free = get_free_rooms(occ_list)
    cur.executemany(
        "INSERT OR IGNORE INTO free_rooms "
        "(week, day, start_time, end_time, room) VALUES (?, ?, ?, ?, ?);",
        free
    )

    conn.commit()
    conn.close()
    print("✅ occupied_rooms и free_rooms обновлены.")


if __name__ == "__main__":
    save_filtered_data()
