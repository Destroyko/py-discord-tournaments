# py-discord-tournaments

Discord-бот на Python для регистрации участников на турниры faceit через штатные формы Discord (Modals), без использования faceit API.

Полное техническое задание: [todo.txt](todo.txt). Архитектура и схема БД: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Установка

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # заполнить своими значениями
```

## Настройка бота в Discord Developer Portal

1. Создать приложение и бота на https://discord.com/developers/applications.
2. Вкладка Bot -> скопировать токен в `DISCORD_TOKEN`.
3. Пригласить бота на сервер со scope `bot applications.commands` и правами: `Send Messages`, `Embed Links`, `Use Application Commands`, `View Channel` (в нужных каналах).
4. После первого запуска бота — в настройках сервера, вкладка **Integrations**, найти бота и настроить, каким ролям разрешено использовать команды `/tournament_active` и `/tournament_join` (второй уровень защиты поверх проверки ролей в коде).
5. Заполнить `.env`: айди гильдии, каналов и ролей (см. `.env.example`).

## Запуск

```bash
python -m bot.main
```

При старте бот выполняет самопроверку (подключение к гильдии, наличие каналов/ролей из конфига, права бота) и пишет результат в лог. Если проверка не пройдена — бот останавливается, причина — в логе.

## Продакшн-деплой (systemd)

Пример unit-файла: [deploy/discord-bot.service](deploy/discord-bot.service). Скопировать в `/etc/systemd/system/`, поправить пути и пользователя, затем:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now discord-bot.service
sudo journalctl -u discord-bot.service -f
```

Файл БД (`DB_PATH`, по умолчанию `tournaments.db`) — единственное хранилище истории заявок, стоит включить его в регулярные бэкапы сервера.
