import sqlite3
import datetime
import re
from collections import defaultdict
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build

# Идентификатор вашего календаря
CALENDAR_ID = 'XXX@group.calendar.google.com'
SCOPES = ['https://www.googleapis.com/auth/calendar']
SERVICE_ACCOUNT_FILE = 'service_account.json'

# Для примера возьмём московский часовой пояс
MOSCOW_TZ = datetime.timezone(datetime.timedelta(hours=3))


def get_calendar_service():
    """
    Создает и возвращает объект сервиса Google Calendar,
    используя данные сервисного аккаунта.
    """
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    service = build('calendar', 'v3', credentials=credentials)
    return service


def ensure_google_event_id_column():
    """
    Проверяет наличие столбца google_event_id в таблице occupied_rooms.
    Если столбца нет, добавляет его.
    """
    conn = sqlite3.connect("mai_schedule.db")
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(occupied_rooms)")
    columns = [col[1] for col in cursor.fetchall()]
    if "google_event_id" not in columns:
        print("Столбец google_event_id отсутствует. Добавляем его...")
        cursor.execute("ALTER TABLE occupied_rooms ADD COLUMN google_event_id TEXT")
        conn.commit()
    conn.close()


def parse_date_str(day_str):
    """
    Преобразует строку вида "Пн, 17 марта" или "Пн, 17 марта 2025"
    в объект datetime.date.
    Если год не указан, подставляем текущий или следующий год,
    если дата сильно в прошлом.
    """
    months = {
        "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
        "мая": 5, "июня": 6, "июля": 7, "августа": 8,
        "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
    }
    match = re.search(r'(\d{1,2})\s+([а-яА-Я]+)(?:\s+(\d{4}))?', day_str)
    if match:
        day_num = int(match.group(1))
        month_word = match.group(2).lower()
        if match.group(3):
            year = int(match.group(3))
        else:
            year = datetime.datetime.now().year
        if month_word in months:
            candidate = datetime.date(year, months[month_word], day_num)
            today = datetime.date.today()
            # Если полученная дата более чем на 60 дней в прошлом, предполагаем, что это следующий год
            if candidate < today and (today - candidate).days > 60:
                candidate = datetime.date(year + 1, months[month_word], day_num)
            return candidate
    return None


def sync_events_in_date_range(start_date: datetime.date, end_date: datetime.date):
    """
    Синхронизирует события из occupied_rooms, у которых дата (поле day)
    попадает в интервал [start_date, end_date].

    События группируются по (week, day, time, room, subject, teacher).
    В описание добавляются все группы, у которых совпадают эти поля.
    """
    ensure_google_event_id_column()
    service = get_calendar_service()

    conn = sqlite3.connect("mai_schedule.db")
    cursor = conn.cursor()

    # Выбираем все записи
    cursor.execute("""
        SELECT 
            rowid,
            week, 
            day,
            time,
            room,
            subject,
            teacher,
            group_name,
            weekday,
            google_event_id
        FROM occupied_rooms
    """)
    rows = cursor.fetchall()

    conn.close()

    # Отфильтровываем только те записи, которые попадают в нужный диапазон дат
    filtered_rows = []
    for row in rows:
        rowid, week, day_str, time_str, room, subject, teacher, group_name, weekday, google_event_id = row
        date_obj = parse_date_str(day_str)
        if not date_obj:
            continue
        # Если дата в диапазоне [start_date, end_date], включаем запись
        if start_date <= date_obj <= end_date:
            filtered_rows.append(row)

    if not filtered_rows:
        print("Нет записей для синхронизации в указанный период.")
        return

    # Группируем по ключу (week, day, time, room, subject, teacher)
    from collections import defaultdict
    events_dict = defaultdict(lambda: {
        "rowids": [],
        "groups": set(),
        "google_event_id": None,
        "day_str": None,
        "time_str": None
    })

    for row in filtered_rows:
        rowid, week, day_str, time_str, room, subject, teacher, group_name, weekday, google_event_id = row
        key = (week, day_str, time_str, room, subject, teacher)
        events_dict[key]["rowids"].append(rowid)
        events_dict[key]["groups"].add(group_name)
        events_dict[key]["day_str"] = day_str
        events_dict[key]["time_str"] = time_str
        if google_event_id:
            events_dict[key]["google_event_id"] = google_event_id

    conn = sqlite3.connect("mai_schedule.db")
    cursor = conn.cursor()

    for key, data in events_dict.items():
        week, day_str, time_str, room, subject, teacher = key
        group_names = sorted(data["groups"])
        aggregated_groups = ", ".join(group_names)
        google_event_id = data["google_event_id"]
        rowids = data["rowids"]

        # Парсим дату ещё раз
        date_obj = parse_date_str(day_str)
        if not date_obj:
            print(f"Не распознана дата: {day_str}")
            continue

        parts = time_str.split(" - ")
        if len(parts) != 2:
            print(f"Формат времени не соответствует 'HH:MM - HH:MM': {time_str}")
            continue
        start_str, end_str = parts[0].strip(), parts[1].strip()

        try:
            start_dt = datetime.datetime.combine(
                date_obj,
                datetime.datetime.strptime(start_str, "%H:%M").time()
            )
            end_dt = datetime.datetime.combine(
                date_obj,
                datetime.datetime.strptime(end_str, "%H:%M").time()
            )
        except Exception as e:
            print(f"Ошибка разбора времени '{time_str}': {e}")
            continue

        event_body = {
            'summary': subject,
            'location': room,
            'description': f"Преподаватель: {teacher}\nГруппы: {aggregated_groups}\nНеделя: {week}",
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': 'Europe/Moscow',
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': 'Europe/Moscow',
            },
        }

        try:
            if google_event_id:
                updated_event = service.events().update(
                    calendarId=CALENDAR_ID,
                    eventId=google_event_id,
                    body=event_body
                ).execute()
                new_event_id = updated_event['id']
                print(f"Обновлено событие {new_event_id} (неделя {week}, {day_str}, {time_str}, {room})")
            else:
                created_event = service.events().insert(
                    calendarId=CALENDAR_ID,
                    body=event_body
                ).execute()
                new_event_id = created_event['id']
                print(f"Создано событие {new_event_id} (неделя {week}, {day_str}, {time_str}, {room})")

            # Обновляем google_event_id для всех записей
            for rowid in rowids:
                cursor.execute("""
                    UPDATE occupied_rooms
                    SET google_event_id = ?
                    WHERE rowid = ?
                """, (new_event_id, rowid))
            conn.commit()

        except Exception as e:
            print(f"Ошибка синхронизации для события {key}: {e}")

    conn.close()
    print("Синхронизация завершена!")


def main():
    """
    Запрашиваем у пользователя начальную и конечную дату в формате DD.MM.YYYY,
    синхронизируем только те записи, у которых day попадает в диапазон.
    """
    start_date_str = input("Введите дату начала (DD.MM.YYYY): ").strip()
    end_date_str = input("Введите дату конца (DD.MM.YYYY): ").strip()

    try:
        start_date = datetime.datetime.strptime(start_date_str, "%d.%m.%Y").date()
        end_date = datetime.datetime.strptime(end_date_str, "%d.%m.%Y").date()
    except ValueError as e:
        print(f"Ошибка при разборе дат: {e}")
        sys.exit(1)

    if end_date < start_date:
        print("Дата конца раньше даты начала! Исправьте и запустите снова.")
        sys.exit(1)

    print(f"Синхронизируем события с {start_date} по {end_date} ...")
    sync_events_in_date_range(start_date, end_date)


if __name__ == "__main__":
    main()
