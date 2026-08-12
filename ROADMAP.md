# Roadmap

---

# Phase 1 — Foundation

Цель: подготовить фундамент проекта.

## Задачи

- [ ] Создать структуру проекта
- [ ] Настроить FastAPI
- [ ] Настроить PostgreSQL
- [ ] Подключить SQLAlchemy
- [ ] Настроить Alembic
- [x] Настроить Docker
- [x] Настроить конфигурацию проекта
- [x] Подключить Telegram Bot
- [ ] Настроить логирование
- [ ] Настроить тестирование

---

# Phase 2 — AI Core

Цель: создать ядро интеллектуальной системы.

## Задачи

- [x] AI Service (пока только как LLM-фолбэк в Conversation Engine, см. specs/003-conversation.md)
- [ ] Prompt Builder
- [ ] Context Engine
- [x] Conversation Engine (rule-based + AI-фолбэк, см. specs/003-conversation.md)
- [x] Long-term Memory
- [ ] Short-term Memory

---

# Phase 3 — Productivity

Цель: создать основные инструменты управления жизнью.

## Задачи

- [x] Planner (приоритет + сортировка как атрибут Tasks, см. specs/002-tasks.md)
- [x] Tasks
- [x] Goals
- [x] Habits
- [x] Journal (через Memory type=journal + Conversation JOURNAL_ENTRY, см. specs/003-conversation.md)
- [ ] Calendar

---

# Phase 4 — Automation

Цель: автоматизировать ежедневные процессы.

## Задачи

- [x] Scheduler
- [x] Notifications (напоминания по due_date задач, см. specs/002-tasks.md)
- [ ] Daily Review
- [ ] Weekly Review
- [x] Morning Briefing
- [x] Evening Reflection (упрощённая версия без диалогового состояния, см. flows/005-evening-reflection.md)

---

# Phase 5 — Analytics

Цель: анализировать действия пользователя.

## Задачи

- [ ] Reports
- [ ] Statistics
- [ ] Productivity Analytics
- [ ] Personal Insights

---

# MVP

Первая рабочая версия должна уметь:

- помнить пользователя;
- работать через Telegram;
- хранить долгосрочную память;
- вести список задач;
- помогать планировать день;
- делать ежедневный обзор;
- отвечать с учетом контекста.