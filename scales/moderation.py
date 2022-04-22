import datetime
import uuid
from pathlib import Path
from typing import Optional

import dis_snek
import motor
from dis_snek import slash_command, slash_option, OptionTypes, SlashCommandChoice, check, InteractionContext, \
    Permissions, Member, Embed
from dis_snek.models import (
    Scale
)
from dpytools.errors import InvalidTimeString
from dpytools.parsers import to_timedelta
import motor.motor_asyncio


mongoConnectionString = (Path(__file__).parent.parent / "mongo.txt").read_text().strip()


def dumb_time(delta: datetime.timedelta) -> Optional[str]:
    if delta.total_seconds() <= 0:
        return "<:error:943118535922679879> I'm not sure what you expected, but I can't mute members in the past"


# https://stackoverflow.com/a/50358747/5616971
def calcEpochSec(dt):
    epochZero = datetime.datetime(1970, 1, 1, tzinfo=dt.tzinfo)
    return (dt - epochZero).total_seconds()


class Moderation(Scale):
    @slash_command(name="mute", description="Mute a user")
    @slash_option(name="user", description="User to mute", opt_type=OptionTypes.USER, required=True)
    @slash_option(
        name="reason",
        description="Reason for mute",
        opt_type=OptionTypes.STRING,
        required=True,
    )
    @slash_option(
        name="time",
        description="Duration of mute, default 1 hour",
        opt_type=OptionTypes.STRING,
        required=False,
    )
    async def _timeout(
        self, ctx: InteractionContext, user: Member, reason: str, time: str = "1h"
    ) -> None:
        client = motor.motor_asyncio.AsyncIOMotorClient(
            mongoConnectionString,
            serverSelectionTimeoutMS=5000)
        db = client.mutes
        if Permissions.MODERATE_MEMBERS not in ctx.author.guild_permissions:
            await ctx.send("<:error:943118535922679879> You are missing the permission `MODERATE_MEMBERS`\n"
                           "Ask a server admin to give you a role with this permission", ephemeral=True)
            return
        if user.top_role > ctx.author.top_role:
            await ctx.send("<:error:943118535922679879> You cannot mute a user with a higher role than you", ephemeral=True)
            return
        if user == ctx.author:
            await ctx.send("You played yourself, oh wait. You can't.\n"
                           "<:error:943118535922679879> You cannot mute yourself.", ephemeral=True)
            return
        if user == self.bot.user:
            await ctx.send("Nice try smarty pants\n"
                           "<:error:943118535922679879> You cannot mute me", ephemeral=True)
            return
        if len(reason) > 100:
            await ctx.send("<:error:943118535922679879> Reason must be < 100 characters", ephemeral=True)
            return
        try:
            time = to_timedelta(time)
        except InvalidTimeString as e:
            await ctx.send(
                "<:error:943118535922679879> That doesn't look like a valid time. Please enter the time in the format of <number>[s|m|h|d|w]",
                ephemeral=True)
            return
        if dumb_time_string := dumb_time(time):
            await ctx.send(dumb_time_string)
            return
        # Max 4 weeks (2419200 seconds) per API
        now = datetime.datetime.now()
        when = now + time
        when_timestamp = str(when.timestamp()).split(".")
        duration = datetime.datetime.now() + time
        if duration.timestamp() > 2419200:  # max time allowed by discord, so we will add it to the db to check and re-apply
            await db.all_mutes.insert_one({
                'guild_id': ctx.guild_id,
                'user_id': ctx.author.id,
                'duration': duration,
                'reason': reason,
                'muted_by': ctx.author.id,
                'uuid': str(uuid.uuid4()),
                'active': True,
            })
        try:
            await user.timeout(communication_disabled_until=duration, reason=reason)
        except dis_snek.errors.Forbidden:
            await ctx.send("<:error:943118535922679879> I do not have the required permissions to mute that user.\n"
                           "Please ensure I am higher in the guild role hierarchy than them.")
            return
        embed = Embed(
            title="<:timeout:958976650450731038> User Muted",
            description=f"{user.mention} has been muted",
            )
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Muted until", value=f"<t:{when_timestamp[0]}:F> (<t:{when_timestamp[0]}:R>)")
        embed.add_field(name="Muted by:", value=ctx.author.display_name)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"{user.username}#{user.discriminator} | {user.id}")
        await ctx.send(embed=embed)

    @slash_command(name="unmute", description="Unmute a user")
    @slash_option(
        name="user", description="User to unmute", opt_type=OptionTypes.USER, required=True
    )
    async def _unmute(self, ctx: InteractionContext, user: Member) -> None:
        if user == ctx.author:
            await ctx.send("If only it was that easy\n"
                           "<:error:943118535922679879> You cannot unmute yourself.")
            return
        if Permissions.MODERATE_MEMBERS not in ctx.author.guild_permissions:
            await ctx.send("<:error:943118535922679879> You are missing the permission `MODERATE_MEMBERS`\n"
                           "Ask a server admin to give you a role with this permission", ephemeral=True)
            return
        if user.top_role > ctx.author.top_role:
            await ctx.send("<:error:943118535922679879> You cannot unmute a user with a higher role than you", ephemeral=True)
            return
        if user.communication_disabled_until is not None:
            dt = user.communication_disabled_until
            disabled_until = calcEpochSec(dt)
            if disabled_until < datetime.datetime.now().timestamp():
                await ctx.send("<:error:943118535922679879> User is not muted", ephemeral=True)
                return

        if not user.communication_disabled_until:
            await ctx.send("<:error:943118535922679879> User is not muted", ephemeral=True)
            return

        embed = Embed(
            title="User Unmuted",
            description=f"{user.mention} has been unmuted"
        )
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.set_footer(text=f"{user.username}#{user.discriminator} | {user.id}")
        await ctx.send(embed=embed)


def setup(bot):
    Moderation(bot)
