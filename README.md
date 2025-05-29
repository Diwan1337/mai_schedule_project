
# 🚀 MAI Schedule Service

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python)
![Flask](https://img.shields.io/badge/flask-2.x-orange?logo=flask)
![React](https://img.shields.io/badge/react-18.x-blue?logo=react)
![Tailwind CSS](https://img.shields.io/badge/tailwindcss-^3.0-teal?logo=tailwind-css)
![SQLite](https://img.shields.io/badge/sqlite-3.x-lightgrey?logo=sqlite)
![MIT License](https://img.shields.io/badge/license-MIT-green)

> **“Mission-critical scheduling for MAI’s IT auditoriums — end-to-end, from scraper to web UI.”**

---

## 🔥 Why This Project Rocks

- **Full-stack** “MAI Schedule” solution: parser ▶️ API ▶️ web UI  
- **Automated** Selenium-driven scraping of MAI’s official timetable  
- **REST-first** Flask backend with **JWT** auth & role-based permissions  
- **Real-time** Google Calendar sync — auto-create, update & delete events  
- **Responsive** single-page frontend for students, teachers & admins  
- **Lightweight** SQLite infrastructure — simple, embeddable, zero-ops  

---

## 📊 Tech Stack Breakdown

| Component           | Technology               | % of Codebase |
|---------------------|--------------------------|:-------------:|
| **Backend**         | Python 3.9+, Flask       |      50%      |
| **Parser**          | Selenium, undetected-chromedriver | 15% |
| **Database**        | SQLite3                  |      10%      |
| **Calendar Sync**   | Google Calendar API      |       5%      |
| **Frontend**        | HTML5, CSS3, Vanilla JS (Axios, Bootstrap) | 15% |
| **CI / Infra**      | GitHub Actions, Docker   |       5%      |

---

## 🏗 Project Structure

```text
mai_schedule_project/
├── backend/
│   ├── parser/                 # 🤖 Schedule crawler (Selenium)
│   │   ├── parser.py           # • Entry point: --weeks flag  
│   │   └── groups_parser.py    # • Fetches group list  
│   │
│   ├── database/               # 💾 SQLite schema & filter logic
│   │   ├── database.py         # • DB init, query/execute helpers  
│   │   └── filter_db.py        # • Occupied/free room generation  
│   │
│   ├── api/                    # 🛠 Flask REST API + Google sync
│   │   ├── routes.py           # • CRUD endpoints, JWT auth  
│   │   ├── google_sync.py      # • Calendar insert/update/delete  
│   │   └── delete_events.py    # • Bulk-delete helper  
│   │
│   └── notifier/               # 🔔 (future) email/push notifications
│
├── frontend/                   # 🌐 Single-Page App
│   ├── index.html              # • React-free HTML + Bootstrap  
│   ├── script.js               # • Axios calls, dynamic table  
│   └── styles.css              # • Custom UI tweaks  
│
├── docs/                       # 📝 Design & requirements
│   ├── Business_Requirements.docx
│   └── System_Requirements.docx
│
├── .github/                    # 🚧 CI/CD workflows
│   └── ci.yml
│
├── Dockerfile                  # 🐳 Containerized service
├── .dockerignore
├── requirements.txt            # 📦 Python dependencies
└── README.md                   # 📘 This file
````

---

## ⚡ Key Features

1. **Parser**

   * Headless, stealth scraping of MAI’s schedule
   * Command-line flags for week ranges, group filters

2. **Database**

   * Auto-migrates schema on startup
   * Computes “occupied” vs. “free” slots for IT rooms
   * Persists `google_event_id` for two-way sync

3. **API**

   * **Public**:

     * `GET /groups` — list all group names
     * `GET /schedule?group=<G>&week=<W>` — group timetable
     * `GET /occupied_rooms` / `GET /free_rooms` — room availability
   * **Protected (JWT)**:

     * `POST /schedule` — add custom slot
     * `PUT /schedule/:id` — modify slot
     * `DELETE /schedule/:id` — delete slot
     * `POST /calendar/sync_group` — manual sync

4. **Google Calendar Sync**

   * Automatic creation, update, deletion
   * Aggregates multiple groups in one event if needed

5. **Frontend**

   * Dynamic, filterable timetable view
   * CRUD UI for teachers & admins
   * One-click Google sync trigger

---

## 🛠 Installation & Quickstart

```bash
# 1. Clone & enter
git clone https://github.com/Diwan1337/mai_schedule_project.git
```
````
cd mai_schedule_project
````
# 2. Python environment
````
python -m venv .venv
````
````
source .venv/bin/activate      # macOS/Linux
````
````
.\.venv\Scripts\activate       # Windows
````
````
pip install -r requirements.txt
````

# 3. Configure Google Calendar credentials
````
cp backend/api/service_account.example.json backend/api/service_account.json
````
# Edit backend/api/google_sync.py → SERVICE_ACCOUNT_FILE, CALENDAR_ID

# 4. Run parser
````
cd backend/parser
````
````
python parser.py --weeks 1,2,3
````
# 5. Start API server
````
python -m backend.api.routes
````

# 6. Open frontend
````
cd ../../frontend
````
# Simply open index.html in your browser (it calls API on 127.0.0.1:5000)



---

## 🤝 Contributing

1. **Fork** & branch
2. **Implement** feature / bugfix
3. **Commit** with clear message:

   ```bash
   git commit -m "feat(parser): support multi-week scrape"
   ```
4. **Push** & open a **Pull Request**
5. ✅ Ensure CI green & reviewers approve

---

## 📜 License

MIT © [MAI Schedule Team](https://github.com/Diwan1337)
