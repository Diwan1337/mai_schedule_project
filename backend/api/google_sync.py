import os
import sys
import sqlite3
import datetime
import re
from collections import defaultdict
from google.oauth2 import service_account
from googleapiclient.discovery import build

from backend.database.database import DB_PATH  # единственный источник пути к БД

# Параметры Google Calendar API
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, "service_account.json")
CALENDAR_ID = "be410167da6282a13f52aad85d4ab444e8b456ecaf5da50495e0b782b566426f@group.calendar.google.com"
SCOPES = ["https://www.googleapis.com/auth/calendar"]
MOSCOW_TZ = datetime.timezone(datetime.timedelta(hours=3))


def get_calendar_service():
    """Создаёт сервис Google Calendar из service_account.json."""
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        print(f"Файл учетных данных не найден: {SERVICE_ACCOUNT_FILE}")
        sys.exit(1)
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    return build("calendar", "v3", credentials=creds)


def ensure_google_event_id_column():
    """Добавляет колонку google_event_id в occupied_rooms, если её нет."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(occupied_rooms)")
    cols = [c[1] for c in cur.fetchall()]
    if "google_event_id" not in cols:
        cur.execute("ALTER TABLE occupied_rooms ADD COLUMN google_event_id TEXT")
        conn.commit()
    conn.close()


def parse_date_str(day_str: str) -> datetime.date | None:
    """
    Парсит строку вида '12 мая' или '12 мая 2025' в datetime.date.
    Если год не указан — берёт текущий, и если дата давно в прошлом (>60 дней),
    переключается на следующий год.
    """
    m = re.match(r'(\d{1,2})\.(\d{1,2})\.(\d{4})$', day_str)
    if m:
        d, mo, y = map(int, m.groups())
        try:
            return datetime.date(y, mo, d)
        except ValueError:
            return None

    months = {
        "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
        "мая": 5, "июня": 6, "июля": 7, "августа": 8,
        "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
    }
    match = re.search(r'(\d{1,2})\s+([а-яА-Я]+)(?:\s+(\d{4}))?', day_str)
    if not match:
        return None

    day_num = int(match.group(1))
    month_word = match.group(2).lower()
    year = int(match.group(3)) if match.group(3) else datetime.date.today().year

    if month_word not in months:
        return None

    candidate = datetime.date(year, months[month_word], day_num)
    today = datetime.date.today()
    # если дата слишком давно в прошлом, переключаемся на следующий год
    if candidate < today and (today - candidate).days > 60:
        candidate = datetime.date(year + 1, months[month_word], day_num)
    return candidate


def sync_group_to_calendar(group_name: str):
    """
    Синхронизирует все записи occupied_rooms для заданной группы в Google Calendar:
    создаёт новые события или обновляет по google_event_id.
    """
    print(f"[GOOGLE_SYNC] sync_group_to_calendar вызван для группы: {group_name}")
    ensure_google_event_id_column()
    service = get_calendar_service()

    # Читаем данные из occupied_rooms (вместо PARSER_DB — единый DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT o.rowid, o.week, o.day, o.start_time, o.end_time,
            o.room, o.subject, o.teacher, o.group_name, o.google_event_id
        FROM occupied_rooms o
        JOIN schedule      s ON s.id = o.schedule_id
        WHERE o.group_name = ?
            AND s.is_custom  = 1
    """, (group_name,))
    rows = cursor.fetchall()
    # Не закрываем курсор, т.к. придётся обновлять google_event_id ниже
    # conn.close() пока отложим

    # Группируем по одинаковым событиям
    events_dict = defaultdict(lambda: {
        "rowids": [], "groups": set(), "google_event_id": None,
        "day_str": None, "time_str": None
    })
    for (rowid, week, day_str, start_t, end_t,
         room, subject, teacher, group_name, google_event_id) in rows:
        key = rowid
        data = events_dict[key]
        data["rowids"].append(rowid)
        data["groups"].add(group_name)
        data["week"] = week
        data["day_str"] = day_str
        data["time_str"] = f"{start_t} - {end_t}"
        data["room"] = room
        data["subject"] = subject
        data["teacher"] = teacher
        if google_event_id:
            data["google_event_id"] = google_event_id

    # Обрабатываем каждое уникальное событие
    for rowid, data in events_dict.items():
        week = data["week"]
        day_str = data["day_str"]
        time_str = data["time_str"]
        room = data["room"]
        subject = data["subject"]
        teacher = data["teacher"]
        aggregated_groups = ", ".join(sorted(data["groups"]))
        prev_event_id = data["google_event_id"]

        # Приводим поля к строкам
        subject = str(subject) if subject else "No Subject"
        teacher = str(teacher) if teacher else ""
        room = str(room) if room else ""

        # Разбираем дату и время
        event_date = parse_date_str(day_str)
        if not event_date:
            print(f"[GOOGLE_SYNC] Не распознана дата: {day_str}")
            continue

        start_str, end_str = time_str.split(" - ")
        try:
            start_dt = datetime.datetime.combine(event_date,
                                                 datetime.datetime.strptime(start_str, "%H:%M").time())
            end_dt = datetime.datetime.combine(event_date,
                                               datetime.datetime.strptime(end_str, "%H:%M").time())
        except Exception as e:
            print(f"[GOOGLE_SYNC] Ошибка парсинга времени '{time_str}': {e}")
            continue

        # Формируем тело события
        event_body = {
            'summary': subject,
            'location': room,
            'description': f"Преподаватель: {teacher}\nГруппы: {aggregated_groups}\nНеделя: {week}",
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Europe/Moscow'},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Europe/Moscow'},
        }

        # Создаём или обновляем событие
        try:
            if prev_event_id:
                updated = service.events().update(
                    calendarId=CALENDAR_ID,
                    eventId=prev_event_id,
                    body=event_body
                ).execute()
                new_id = updated['id']
                print(f"[GOOGLE_SYNC] Обновлено событие {new_id}")
            else:
                created = service.events().insert(
                    calendarId=CALENDAR_ID,
                    body=event_body
                ).execute()
                new_id = created['id']
                print(f"[GOOGLE_SYNC] Создано событие {new_id}")

            # Сохраняем google_event_id обратно в БД
            rowids = data["rowids"]
            for rid in rowids:
                cursor.execute(
                    "UPDATE occupied_rooms SET google_event_id = ? WHERE schedule_id = ?",
                    (new_id, rid)
                )
            conn.commit()

        except Exception as e:
            print(f"[GOOGLE_SYNC] Ошибка при синхронизации события {rowid}: {e}")

    conn.close()
    print("[GOOGLE_SYNC] Синхронизация группы завершена!")


def sync_events_in_date_range(start_date: datetime.date, end_date: datetime.date):
    """
    Синхронизирует в Google Calendar все события из occupied_rooms,
    попадающие в диапазон [start_date..end_date].
    """
    print(f"[GOOGLE_SYNC] sync_events_in_date_range: {start_date} — {end_date}")
    ensure_google_event_id_column()
    service = get_calendar_service()

    # Читаем все записи
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT rowid, week, day, start_time, end_time,
               room, subject, teacher, group_name, google_event_id
        FROM occupied_rooms
    """)
    all_rows = cursor.fetchall()

    # Фильтруем по дате
    rows = []
    for (rowid, week, day_str, start_t, end_t,
         room, subject, teacher, group_name, google_event_id) in all_rows:
        date_obj = parse_date_str(day_str)
        if date_obj and start_date <= date_obj <= end_date:
            rows.append((rowid, week, day_str, start_t, end_t,
                         room, subject, teacher, group_name, google_event_id))

    if not rows:
        print("[GOOGLE_SYNC] Нет записей для указанного периода.")
        conn.close()
        return

    # Группируем аналогично sync_group_to_calendar
    events_dict = defaultdict(lambda: {
        "rowids": [], "groups": set(), "google_event_id": None,
        "day_str": None, "time_str": None
    })
    for (rowid, week, day_str, start_t, end_t,
         room, subject, teacher, group_name, google_event_id) in rows:
        time_str = f"{start_t} - {end_t}"
        key = rowid
        events_dict[key]["rowids"].append(rowid)
        events_dict[key]["groups"].add(group_name)
        events_dict[key]["day_str"] = day_str
        events_dict[key]["time_str"] = time_str
        if google_event_id:
            events_dict[key]["google_event_id"] = google_event_id

    # Обрабатываем каждое событие
    for rowid, data in events_dict.items():
        week = data["week"]
        day_str = data["day_str"]
        time_str = data["time_str"]
        room = data["room"]
        subject = data["subject"]
        teacher = data["teacher"]
        aggregated_groups = ", ".join(sorted(data["groups"]))
        prev_event_id = data["google_event_id"]
        rowids = data["rowids"]

        subject = str(subject) if subject else "No Subject"
        teacher = str(teacher) if teacher else ""
        room = str(room) if room else ""

        date_obj = parse_date_str(day_str)
        if not date_obj:
            continue

        start_str, end_str = time_str.split(" - ")
        try:
            start_dt = datetime.datetime.combine(date_obj,
                                                 datetime.datetime.strptime(start_str, "%H:%M").time())
            end_dt = datetime.datetime.combine(date_obj,
                                               datetime.datetime.strptime(end_str, "%H:%M").time())
        except Exception as e:
            print(f"[GOOGLE_SYNC] Ошибка парсинга времени '{time_str}': {e}")
            continue

        event_body = {
            'summary': subject,
            'location': room,
            'description': f"Преподаватель: {teacher}\nГруппы: {aggregated_groups}\nНеделя: {week}",
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': 'Europe/Moscow'},
            'end': {'dateTime': end_dt.isoformat(), 'timeZone': 'Europe/Moscow'},
        }

        try:
            if prev_event_id:
                updated = service.events().update(
                    calendarId=CALENDAR_ID,
                    eventId=prev_event_id,
                    body=event_body
                ).execute()
                new_id = updated['id']
                print(f"[GOOGLE_SYNC] Обновлено событие {new_id}")
            else:
                created = service.events().insert(
                    calendarId=CALENDAR_ID,
                    body=event_body
                ).execute()
                new_id = created['id']
                print(f"[GOOGLE_SYNC] Создано событие {new_id}")

            for rid in rowids:
                cursor.execute(
                    "UPDATE occupied_rooms SET google_event_id = ? WHERE rowid = ?",
                    (new_id, rid)
                )
            conn.commit()

        except Exception as e:
            print(f"[GOOGLE_SYNC] Ошибка при синхронизации события {rowid}: {e}")

    conn.close()
    print("[GOOGLE_SYNC] Синхронизация по диапазону завершена!")


if __name__ == "__main__":
    # Можно протестировать напрямую:
    # sync_group_to_calendar("М8О-110БВ-24")
    # sync_events_in_date_range(datetime.date(2025,5,10), datetime.date(2025,5,17))
    pass
