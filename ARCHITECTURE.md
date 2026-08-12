# Architecture

## Общая схема

```
                Telegram
                    │
                    ▼
          Conversation Engine
                    │
                    ▼
             Intent Router
                    │
      ┌─────────────┼─────────────┐
      ▼             ▼             ▼
  Planner        Memory       AI Service
      ▼             ▼             ▼
 Repository    Repository    Repository
      └─────────────┼─────────────┘
                    ▼
               PostgreSQL
```

---

# Главный принцип

LLM никогда не обращается к базе данных напрямую.

Все операции проходят через сервисный слой.

```
LLM

↓

Service

↓

Repository

↓

Database
```

---

# Основные сервисы

- AI
- Memory
- Planner
- Goals
- Habits
- Journal
- Notifications
- Analytics
- Telegram
- Scheduler
- Settings

---

# Структура проекта

```
app/
│
├── api/
├── core/
├── models/
├── repositories/
├── services/
│
├── ai/
├── memory/
├── planner/
├── telegram/
├── notifications/
│
└── main.py
```

---

# Основные правила

- Каждый сервис отвечает только за одну область.
- Сервисы не должны зависеть друг от друга напрямую.
- Репозитории работают только с базой данных.
- Вся бизнес-логика находится в сервисах.
- API не содержит бизнес-логики.
- LLM не имеет прямого доступа к базе данных.