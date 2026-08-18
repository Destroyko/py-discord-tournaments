# Архитектура

Однo-гильдийный Discord-бот на `discord.py` (slash-команды + Modals + Views), хранение — SQLite через `aiosqlite`.

## Структура кода

```
bot/
  main.py          — точка входа: сборка бота, setup_hook (подключение БД, sync команд на гильдию), on_ready (самопроверка)
  config.py        — загрузка и валидация .env в неизменяемый Config
  db.py            — слой доступа к SQLite: схема, состояние турнира, циклы регистрации, заявки
  checks.py        — проверка ролей пользователя (manager/participant)
  rules.py         — шаблонный текст правил турнира (редактируется в коде)
  startup_checks.py— проверка связи с гильдией, наличия каналов/ролей из конфига, прав бота
  cogs/
    tournament.py  — команды /tournament_active, /tournament_join, TournamentJoinModal, ConfirmView
```

## Модель данных (SQLite)

**state** (одна строка, id=1) — текущее состояние турнира:
- `tournament_name` — название текущего/последнего турнира
- `is_active` — включена ли регистрация сейчас
- `current_cycle_id` — id текущего (или последнего) цикла регистрации

**registration_cycles** — история включений/выключений регистрации:
- `id`, `tournament_name` (название на момент открытия цикла), `opened_at`, `closed_at` (NULL пока открыт), `opened_by`

**applications** — поданные заявки:
- `id`, `cycle_id` (FK), `discord_user_id`, `discord_username`, `faceit_link`, `steam_link`, `comment`, `submitted_at`
- `UNIQUE(cycle_id, discord_user_id)` — гарантирует одну заявку на пользователя за цикл даже при гонке запросов

Данные не удаляются между циклами — вся история остаётся в БД, привязанная к своему `cycle_id`.

## Жизненный цикл регистрации

1. Модератор вызывает `/tournament_active registration:true name:"..."` в `SETUP_CHANNEL_ID`.
2. Создаётся новая строка в `registration_cycles`, `state` обновляется (`is_active=1`, новый `current_cycle_id`).
3. Участники вызывают `/tournament_join` в `REGISTRATION_CHANNEL_ID` — если активно и роль подходит, открывается `TournamentJoinModal`.
4. После отправки формы — повторная проверка активности/дубликата, затем ephemeral-сообщение с текстом правил (`rules.py`) и кнопкой «Подтвердить» (`ConfirmView`, таймаут 180 с).
5. По нажатию кнопки — ещё одна проверка активности, вставка в `applications` (уникальное ограничение страхует от гонки), при успехе — embed в `NOTIFICATION_CHANNEL_ID` (если `POST_TO_CHANNEL_ENABLED=true`).
6. Модератор вызывает `/tournament_active registration:false` — цикл закрывается (`closed_at`, `is_active=0`), `/tournament_join` перестаёт принимать заявки.

## Права доступа

Два независимых уровня:
1. **В коде** — `checks.is_manager` / `checks.is_participant` проверяют роли пользователя из `interaction.user.roles` в момент каждого взаимодействия (не кэшируется).
2. **В Discord** — команды имеют `default_permissions` как базовый уровень; администратор сервера донастраивает доступ по ролям во вкладке Integrations (см. README).

Обе команды дополнительно ограничены конкретным каналом (`SETUP_CHANNEL_ID` / `REGISTRATION_CHANNEL_ID`) — проверка по `interaction.channel_id`.

## Известные ограничения (осознанно)

- Бот одно-гильдийный, мульти-сервер не поддерживается.
- Если бот перезапустится между отправкой модалки и нажатием кнопки «Подтвердить», незавершённая заявка теряется (ещё не была записана в БД) — это принято как приемлемое ограничение.
