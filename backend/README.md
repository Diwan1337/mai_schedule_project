## Оглавление

1. [Описание](#описание)  
2. [Требования](#требования)  
3. [Установка](#установка)  
4. [Модуль Database](#модуль-database)  
5. [Модуль Parser](#модуль-parser)  
6. [Модуль API](#модуль-api)  
7. [Примеры запуска](#примеры-запуска)  

---

## Описание

Этот репозиторий состоит из трёх основных частей:

- **database** — работа с SQLite (создание схемы, CRUD для групп и кеша расписания).  
- **parser** — многопоточный парсер веб-страниц расписания МАИ, сохраняет результаты в JSON-кеш и в БД.  
- **api** — Flask-сервис, отдаёт расписание по HTTP, поддерживает простую JWT-подобную авторизацию и синхронизацию с Google Calendar.

---

## Требования

- Python 3.9+  
- Google Chrome (последняя версия)  
- Пакеты из `requirements.txt` (Selenium, undetected-chromedriver, Flask и др.)  
- SQLite (встроена в Python)  

---

## Модуль Database

Файл: `backend/database/database.py`

* **Путь до БД**: `backend/mai_schedule.db`
* **Основные функции**:

  * `create_tables()` — создаёт все таблицы (`users`, `groups`, `parser_pairs`, `schedule`, `occupied_rooms`, `free_rooms`, `changes_log`).
  * `get_connection()` — возвращает `sqlite3.Connection`.
  * `init_db(conn)` — создаёт таблицы `groups` и `parser_pairs` для парсера.
  * `get_groups_with_id()` — список групп из БД.
  * `get_cached_pairs(conn, group_id, week)` — возвращает JSON-кеш расписания.
  * `save_pairs(conn, group_id, week, data)` — сохраняет или обновляет JSON-кеш.
  * `save_schedule(conn, group_id, week, data)` — развёртывает пары из кеша в таблицу `schedule`.

---

## Модуль Parser

Путь: `backend/parser/parser.py`

1. **Получение списка групп**
   Группы предварительно загружаются командой `groups_parser.py` и сохраняются в БД.
2. **Кеширование**

   * JSON-кеш хранится в `backend/parser/cache/<group>_wk<week>.json`.
   * Если данные по (группа, неделя) уже есть в БД и флаг `--force-db` не установлен, парсинг пропускается.
3. **Многопоточность**

   * Опция `--threads` задаёт число параллельных Chrome-дроверов.
   * Дроверы создаются один раз, кладутся в очередь, каждый поток берёт свой драйвер и возвращает обратно.
4. **CLI-опции**:

   * `--weeks 14,15,16` — через запятую список номеров недель.
   * `--force-db` — перезаписать кеш и БД, даже если данные есть.
   * `--threads 5` — число параллельных потоков (дроверов).

---

## Модуль API

Путь: `backend/api/routes.py`

* **Авторизация**
  Простая JWT-подобная: в заголовке `Authorization: Bearer <json>` передаются `{ "user_id": ..., "role": ... }`.
* **Эндпоинты**:

  * `POST /register` — регистрация пользователя (email+password+role).
  * `POST /login` — вход, возвращает «токен» JSON-строкой.
  * `GET  /groups` — список названий групп.
  * `GET  /schedule?group=<>&week=<>` — расписание по группе и неделе.
  * `POST /schedule` — добавление собственного занятия (требует роль `teacher` или `admin`).
  * `GET  /occupied_rooms` — занятые аудитории.
  * `GET  /free_rooms` — свободные аудитории.
  * `POST /calendar/sync_group` — синхронизация всей группы в Google Calendar.
  * `POST /calendar/sync_range` — синхронизация событий по дате (start\_date, end\_date в формате `DD.MM.YYYY`).

---

## Примеры запуска

1. Загрузка групп в БД:

   ```bash
   python -m backend.parser.groups_parser --force-db
   ```
2. Парсинг расписания (недели 14,15,16, 5 потоков):

   ```bash
   python -m backend.parser.parser --weeks 14,15,16 --threads 5
   ```
3. Запуск API-сервера на порту 5000:

   ```bash
   python -m backend.api.routes
   ```
---

## Лицензия

MIT License © 2025
