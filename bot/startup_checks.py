import logging

from discord.ext import commands

from bot.config import Config

log = logging.getLogger("bot.startup_checks")


async def run_startup_checks(bot: commands.Bot, config: Config) -> bool:
    """Проверяет связь с гильдией, наличие каналов/ролей из конфига и прав бота.

    Возвращает False, если бот не готов к работе — вызывающий код должен
    остановить бота, чтобы причина была явно видна в логах (journalctl).
    """
    ok = True

    guild = bot.get_guild(config.guild_id)
    if guild is None:
        log.critical(
            "Бот не состоит в гильдии с id=%s (GUILD_ID). Проверьте приглашение бота на сервер.",
            config.guild_id,
        )
        return False
    log.info("Гильдия найдена: %s (id=%s)", guild.name, guild.id)

    channel_checks = {
        "SETUP_CHANNEL_ID": config.setup_channel_id,
        "REGISTRATION_CHANNEL_ID": config.registration_channel_id,
        "NOTIFICATION_CHANNEL_ID": config.notification_channel_id,
    }
    for var_name, channel_id in channel_checks.items():
        channel = guild.get_channel_or_thread(channel_id)
        if channel is None:
            log.critical("Канал %s=%s не найден в гильдии %s.", var_name, channel_id, guild.id)
            ok = False
            continue
        perms = channel.permissions_for(guild.me)
        missing = [
            perm_name
            for perm_name, has_perm in (
                ("view_channel", perms.view_channel),
                ("send_messages", perms.send_messages),
                ("embed_links", perms.embed_links),
            )
            if not has_perm
        ]
        if missing:
            log.critical(
                "Боту не хватает прав %s в канале #%s (%s=%s).",
                missing, channel.name, var_name, channel_id,
            )
            ok = False
        else:
            log.info("Канал #%s (%s=%s) — права в порядке.", channel.name, var_name, channel_id)

    role_checks = {
        "MANAGER_ROLE_IDS": config.manager_role_ids,
        "PARTICIPANT_ROLE_ID": [config.participant_role_id],
    }
    for var_name, role_ids in role_checks.items():
        for role_id in role_ids:
            role = guild.get_role(role_id)
            if role is None:
                log.critical("Роль %s=%s не найдена в гильдии %s.", var_name, role_id, guild.id)
                ok = False
            else:
                log.info("Роль @%s (%s=%s) найдена.", role.name, var_name, role_id)

    if not guild.me.guild_permissions.use_application_commands:
        log.warning(
            "У бота может не быть права use_application_commands на сервере — "
            "проверьте, что бот приглашён со scope applications.commands."
        )

    return ok
