import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from bot.checks import is_manager, is_participant
from bot.config import Config
from bot.db import Database
from bot.rules import TOURNAMENT_RULES_TEXT

log = logging.getLogger("bot.tournament")

MODAL_TITLE_MAX_LENGTH = 45


class TournamentJoinModal(discord.ui.Modal):
    """Форма заявки. Поля специально сделаны как атрибуты + add_item,
    чтобы в будущем было легко добавить/убрать поле, не переписывая on_submit целиком."""

    def __init__(self, cog: "TournamentCog", cycle_id: int, tournament_name: str):
        title = f"Регистрация: {tournament_name}"[:MODAL_TITLE_MAX_LENGTH]
        super().__init__(title=title)
        self.cog = cog
        self.cycle_id = cycle_id
        self.tournament_name = tournament_name

        self.faceit_link = discord.ui.TextInput(
            label="Ссылка на основной аккаунт faceit",
            style=discord.TextStyle.short,
            placeholder="https://www.faceit.com/ru/players/...",
            required=True,
            max_length=200,
        )
        self.steam_link = discord.ui.TextInput(
            label="Ссылка на основной аккаунт Steam",
            style=discord.TextStyle.short,
            placeholder="https://steamcommunity.com/id/...",
            required=True,
            max_length=200,
        )
        self.comment = discord.ui.TextInput(
            label="Комментарий",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=500,
        )
        self.add_item(self.faceit_link)
        self.add_item(self.steam_link)
        self.add_item(self.comment)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        faceit_link = self.faceit_link.value.strip()
        steam_link = self.steam_link.value.strip()
        comment = self.comment.value.strip() or None

        if not faceit_link.startswith("https://"):
            await interaction.response.send_message(
                "Ссылка на faceit-аккаунт должна начинаться с `https://`. Повторите /tournament_join.",
                ephemeral=True,
            )
            return

        if not steam_link.startswith("https://"):
            await interaction.response.send_message(
                "Ссылка на Steam-аккаунт должна начинаться с `https://`. Повторите /tournament_join.",
                ephemeral=True,
            )
            return

        # Регистрацию/цикл могли закрыть, пока пользователь заполнял форму — перепроверяем.
        state = await self.cog.db.get_state()
        if not state.is_active or state.current_cycle_id != self.cycle_id:
            await interaction.response.send_message(
                "Регистрация была закрыта, пока вы заполняли форму. Заявка не принята.",
                ephemeral=True,
            )
            return

        if await self.cog.db.has_applied(self.cycle_id, interaction.user.id):
            await interaction.response.send_message(
                "Вы уже отправляли заявку на регистрацию в этом турнире.",
                ephemeral=True,
            )
            return

        view = ConfirmView(self.cog, self.cycle_id, self.tournament_name, faceit_link, steam_link, comment)
        await interaction.response.send_message(TOURNAMENT_RULES_TEXT, view=view, ephemeral=True)
        view.message = await interaction.original_response()


class ConfirmView(discord.ui.View):
    def __init__(
        self,
        cog: "TournamentCog",
        cycle_id: int,
        tournament_name: str,
        faceit_link: str,
        steam_link: str,
        comment: Optional[str],
    ):
        super().__init__(timeout=180)
        self.cog = cog
        self.cycle_id = cycle_id
        self.tournament_name = tournament_name
        self.faceit_link = faceit_link
        self.steam_link = steam_link
        self.comment = comment
        self.message: Optional[discord.Message] = None
        self._handled = False

    @discord.ui.button(label="Подтвердить", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self._handled:
            # Двойной клик — второй раз просто гасим взаимодействие, ничего не делаем.
            await interaction.response.defer()
            return
        self._handled = True
        button.disabled = True
        self.stop()
        await interaction.response.edit_message(content="Обработка заявки...", view=self)

        state = await self.cog.db.get_state()
        if not state.is_active or state.current_cycle_id != self.cycle_id:
            await interaction.edit_original_response(
                content="Регистрация уже закрыта, заявка не принята.", view=None
            )
            return

        member = interaction.user
        inserted = await self.cog.db.insert_application(
            cycle_id=self.cycle_id,
            discord_user_id=member.id,
            discord_username=str(member),
            faceit_link=self.faceit_link,
            steam_link=self.steam_link,
            comment=self.comment,
        )
        if not inserted:
            await interaction.edit_original_response(
                content="Вы уже отправляли заявку на регистрацию в этом турнире.", view=None
            )
            return

        await interaction.edit_original_response(
            content="Заявка принята. Спасибо за регистрацию!", view=None
        )
        log.info("Application accepted: user=%s cycle=%s", member.id, self.cycle_id)

        if self.cog.config.post_to_channel_enabled:
            await self.cog.post_notification(
                member, self.faceit_link, self.steam_link, self.comment, self.tournament_name
            )

    async def on_timeout(self) -> None:
        if self._handled:
            return
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(
                    content="Время ожидания подтверждения истекло. Повторите /tournament_join.",
                    view=self,
                )
            except discord.HTTPException:
                pass


class TournamentCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Config, db: Database):
        self.bot = bot
        self.config = config
        self.db = db

    async def post_notification(
        self,
        member: discord.abc.User,
        faceit_link: str,
        steam_link: str,
        comment: Optional[str],
        tournament_name: str,
    ) -> None:
        channel = self.bot.get_channel(self.config.notification_channel_id)
        if channel is None:
            log.warning("Канал уведомлений %s не найден, embed не отправлен.", self.config.notification_channel_id)
            return
        embed = discord.Embed(title=f"Новая заявка — {tournament_name}", color=discord.Color.blurple())
        embed.add_field(name="Участник", value=f"{member.mention} (`{member.id}`)", inline=False)
        embed.add_field(name="Faceit", value=faceit_link, inline=False)
        embed.add_field(name="Steam", value=steam_link, inline=False)
        embed.add_field(name="Комментарий", value=comment or "—", inline=False)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException as exc:
            log.error("Не удалось отправить embed уведомления: %s", exc)

    @app_commands.command(name="tournament_active", description="Включить или выключить регистрацию на турнир")
    @app_commands.describe(
        registration="true — включить регистрацию, false — выключить",
        name="Название турнира (обязательно при первом включении, иначе используется предыдущее)",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def tournament_active(
        self,
        interaction: discord.Interaction,
        registration: bool,
        name: Optional[str] = None,
    ) -> None:
        if interaction.channel_id != self.config.setup_channel_id:
            await interaction.response.send_message(
                f"Эта команда доступна только в <#{self.config.setup_channel_id}>.", ephemeral=True
            )
            return

        member = interaction.user
        if not isinstance(member, discord.Member) or not is_manager(member, self.config.manager_role_ids):
            await interaction.response.send_message("У вас нет прав для использования этой команды.", ephemeral=True)
            return

        if registration:
            state = await self.db.get_state()
            tournament_name = name or state.tournament_name
            if not tournament_name:
                await interaction.response.send_message(
                    "Название турнира обязательно при первом включении регистрации. Укажите параметр name.",
                    ephemeral=True,
                )
                return
            cycle_id = await self.db.open_cycle(tournament_name, opened_by=str(member.id))
            log.info("Registration opened: tournament=%r cycle=%s by=%s", tournament_name, cycle_id, member.id)
            await interaction.response.send_message(
                f"Регистрация на турнир **{tournament_name}** включена (цикл #{cycle_id}).",
                ephemeral=True,
            )
        else:
            state = await self.db.get_state()
            if not state.is_active:
                await interaction.response.send_message("Регистрация и так уже выключена.", ephemeral=True)
                return
            await self.db.close_cycle(closed_by=str(member.id))
            log.info(
                "Registration closed: tournament=%r cycle=%s by=%s",
                state.tournament_name, state.current_cycle_id, member.id,
            )
            await interaction.response.send_message(
                f"Регистрация на турнир **{state.tournament_name}** выключена.", ephemeral=True
            )

    @app_commands.command(name="tournament_join", description="Подать заявку на участие в турнире")
    @app_commands.guild_only()
    async def tournament_join(self, interaction: discord.Interaction) -> None:
        if interaction.channel_id != self.config.registration_channel_id:
            await interaction.response.send_message(
                f"Эта команда доступна только в <#{self.config.registration_channel_id}>.", ephemeral=True
            )
            return

        member = interaction.user
        if not isinstance(member, discord.Member) or not is_participant(member, self.config.participant_role_id):
            await interaction.response.send_message("У вас нет прав для участия в турнире.", ephemeral=True)
            return

        state = await self.db.get_state()
        if not state.is_active or state.current_cycle_id is None:
            await interaction.response.send_message("На данный момент регистрация на турнир закрыта.", ephemeral=True)
            return

        if await self.db.has_applied(state.current_cycle_id, member.id):
            await interaction.response.send_message(
                "Вы уже отправляли заявку на регистрацию в этом турнире.", ephemeral=True
            )
            return

        modal = TournamentJoinModal(self, state.current_cycle_id, state.tournament_name)
        await interaction.response.send_modal(modal)
