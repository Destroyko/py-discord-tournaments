import logging

import discord
from discord.ext import commands

from bot.cogs.tournament import TournamentCog
from bot.config import ConfigError, load_config
from bot.db import Database
from bot.startup_checks import run_startup_checks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("bot.main")

# Код выхода при провале стартовых проверок. systemd не перезапускает процесс с этим кодом
# (см. RestartPreventExitStatus в deploy/discord-bot.service), иначе будет цикл переподключений.
EXIT_STARTUP_CHECKS_FAILED = 3


class TournamentBot(commands.Bot):
    def __init__(self, config):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.config = config
        self.db = Database(config.db_path)
        self.exit_code = 0

    async def setup_hook(self) -> None:
        await self.db.connect()
        await self.add_cog(TournamentCog(self, self.config, self.db))

        guild = discord.Object(id=self.config.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        log.info("Slash-команды синхронизированы с гильдией %s.", self.config.guild_id)

    async def on_ready(self) -> None:
        log.info("Вход выполнен как %s (id=%s).", self.user, self.user.id if self.user else "?")
        ok = await run_startup_checks(self, self.config)
        if not ok:
            log.critical("Проверки при запуске не пройдены — бот останавливается.")
            self.exit_code = EXIT_STARTUP_CHECKS_FAILED
            await self.close()
            return
        log.info("Все проверки пройдены. Бот готов к работе.")

    async def close(self) -> None:
        await self.db.close()
        await super().close()


async def _on_app_command_error(
    interaction: discord.Interaction, error: discord.app_commands.AppCommandError
) -> None:
    log.exception("Ошибка при обработке команды: %s", error)
    message = "Произошла непредвиденная ошибка. Попробуйте позже."
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


def main() -> None:
    try:
        config = load_config()
    except ConfigError as exc:
        log.critical("Ошибка конфигурации: %s", exc)
        raise SystemExit(1) from exc

    bot = TournamentBot(config)
    bot.tree.on_error = _on_app_command_error
    bot.run(config.discord_token, log_handler=None)
    if bot.exit_code:
        raise SystemExit(bot.exit_code)


if __name__ == "__main__":
    main()
