from typing import Iterable

import discord


def has_any_role(member: discord.Member, role_ids: Iterable[int]) -> bool:
    member_role_ids = {role.id for role in member.roles}
    return not member_role_ids.isdisjoint(set(role_ids))


def is_manager(member: discord.Member, manager_role_ids: Iterable[int]) -> bool:
    return has_any_role(member, manager_role_ids)


def is_participant(member: discord.Member, participant_role_id: int) -> bool:
    return has_any_role(member, [participant_role_id])
