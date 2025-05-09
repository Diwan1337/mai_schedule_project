# 💻 MAI Schedule Service

**Веб-сервис для автоматизированного сбора, отображения и синхронизации расписания занятий в компьютерных аудиториях кафедры 806 МАИ**.

---

## 📌 Оглавление

* [Описание](#описание)
* [Особенности](#особенности)
* [Архитектура](#архитектура)
* [Установка](#установка)
* [Использование](#использование)
* [Структура проекта](#структура-проекта)
* [Тестирование](#тестирование)
* [Контрибьютинг](#контрибьютинг)
* [Лицензия](#лицензия)

---

## 📝 Описание

Этот проект позволяет:

* Автоматически **парсить** расписание занятий с официального сайта МАИ с помощью Selenium.
* Сохранять данные локально в SQLite для офлайн-доступа и быстрой фильтрации.
* Предоставлять **REST API** (Flask) для получения расписания, списка групп и свободных/занятых аудиторий.
* Синхронизировать расписание с **Google Calendar** для уведомлений и интеграции.

---

## 🌟 Особенности

* **Парсер расписания** на основе undetected\_chromedriver.
* **Кэширование** полученных групп и заданий (JSON‑файлы).
* **Фильтрация** аудиторий по расписанию (occupied/free rooms).
* **JWT‑авторизация** для CRUD‑операций (роли: student, teacher, admin).
* **Интеграция** с Google Calendar: автоматическое создание/удаление событий.
* **Конфигурируемость**: выбор недель для парсинга, настраиваемые аудиторные фильтры.

---

## 🏗 Архитектура

```text
├── backend/                  # Серверная часть
│   ├── parser/               # Парсер (Selenium)
│   │   ├── parser.py         # Основной скрипт парсера
│   │   ├── groups_parser.py  # Получение списка групп
│   │   └── mai_schedule.db   # БД расписания
│   │
│   ├── database/             # Модуль работы с БД
│   │   ├── database.py       # Функции create/query/execute
│   │   └── filter_db.py      # Фильтрация occupied/free rooms
│   │
│   ├── api/                  # REST API (Flask)
│   │   ├── routes.py         # Определение эндпоинтов
│   │   ├── google_sync.py    # Синхронизация с Google Calendar
│   │   └── delete_events.py  # Удаление событий из Google Calendar
│   │
│   └── notifier/             # (в будущем) уведомления
│
├── frontend/                 # (в будущем) веб‑интерфейс
│
├── docs/                     # Документация
│   ├── Business Requirements.docx
│   └── System Requirements.docx
│
├── requirements.txt          # Python-зависимости
├── .gitignore                # Исключения Git
└── README.md                 # Документация проекта
```

---

## 🚀 Установка

1. **Клонировать репозиторий**:

   ```bash
   git clone https://github.com/Diwan1337/mai_schedule_project.git
   ```
   ```
   cd mai_schedule_project
   ```
2. **Создать и активировать виртуальное окружение**:

   ```bash
   python -m venv .venv
   ```
   # Windows
   ```
   .\.venv\Scripts\activate
   ```
   # Linux/macOS
   ```
   source .venv/bin/activate
   ```
4. **Установить зависимости**:

   ```bash
   pip install -r requirements.txt
   ```

---

## ▶️ Использование

### 1. Парсинг расписания

```bash
cd backend/parser
```
```
python parser.py --weeks 1,2,3
```

### 2. Фильтрация аудиторий

```bash
cd ../database
```
```
python filter_db.py
```

### 3. Запуск API-сервера

```bash
cd ../api
```
```
python -m api.routes
```

### 4. Взаимодействие с API

* Получить список групп: `GET /groups`
* Получить расписание для группы: `GET /schedule?group=G1&week=5`
* Получить занятые кабинеты: `GET /occupied_rooms`
* Добавить занятие (только teacher/admin): `POST /schedule`
* Синхронизировать группу с Google Calendar: `POST /calendar/sync_group` (JWT)

---

## ✅ Тестирование

```bash
cd backend
```
```
python test_routes.py
```

---

## 🤝 Контрибьютинг

1. Сделайте fork репозитория
2. Создайте новую ветку: `git checkout -b feat/your-feature`
3. Внесите изменения и сделайте commit: `git commit -m "feat: описание"`
4. Push в ветку: `git push origin feat/your-feature`
5. Создайте Pull Request

---

## 📄 Лицензия

Проект распространяется под лицензией MIT. Смотри [LICENSE](LICENSE).
