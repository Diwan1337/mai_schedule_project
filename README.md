# 💻 Веб-сервис для отслеживания занятости компьютерных классов 806 кафедры

Этот проект автоматизирует **сбор и отображение расписания** для аудиторий кафедры 806 в МАИ.

## 🚀 Функционал:
✅ **Парсер расписания** (Selenium) — `scraper.py`  
✅ **Фильтрация аудиторий** (IT-кабинеты) — `filter_db.py`  
✅ **API (Flask)** — `api.py`  
✅ **База данных** (SQLite) — `mai_schedule.db`  
🔳 **Интеграция с Google Calendar**  
🔳 **Уведомления преподавателей**  
🔳 **Веб-интерфейс**  

---

## 🔧 Установка и запуск
1️⃣ **Установите Python 3.9+**  
2️⃣ **Склонируйте репозиторий:**
```bash
git clone https://github.com/Diwan1337/mai_schedule_project.git
```
```bash
cd mai_schedule_project
```
3️⃣ Установите зависимости:
```bash
pip install -r requirements.txt
```

📄 Документация:
📂 Бизнес-требования: docs/Business Requirements.docx
📂 Спецификация (SRS): docs/System Requirements.docx

🛠 Текущий статус разработки:
✅ **Парсинг расписания (Selenium)**
✅ **Фильтрация IT-аудиторий**
✅ **Работа с БД (SQLite)**
🔲 Интеграция с Google Calendar
🔲 Уведомления преподавателей
🔲 Гибкое редактирование расписания
🔲 Полноценный веб-интерфейс

👨‍💻 Авторы:
📌 **Резинкин Д.В.**
📌 **Лебедев И.В.**
📌 **Билый А.Б.**
📌 **Телепнева А.В.**

