import subprocess
from functools import cached_property
from typing import TYPE_CHECKING

import aiohttp
import naff
from naff import (
    Extension,
    prefixed_command,
    PrefixedContext,
    check,
    Context,
    slash_command,
    InteractionContext,
    Embed,
    BrandColors,
    Timestamp,
    TimestampStyles,
)
from naff.client.errors import CommandCheckFailure

__all__ = ("is_owner", "setup", "Admin")

if TYPE_CHECKING:
    from main import Bot


def is_owner() -> bool:
    """
    Is the author the owner of the bot.

    parameters:
        coro: the function to check
    """

    async def check(ctx: Context) -> bool:
        return ctx.author.id == 174918559539920897

    return check


class Admin(Extension):
    bot: "Bot"

    @cached_property
    def naff_commit(self) -> str:
        deps = subprocess.check_output(["pip", "freeze"]).decode("ascii").splitlines()
        naff_module = [dep for dep in deps if dep.startswith("naff")][0]
        return naff_module.split("@")[-1]

    @cached_property
    def inquiry_commit(self) -> str:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode("ascii").strip()

    @prefixed_command()
    @check(is_owner())
    async def set_avatar(self, ctx: PrefixedContext) -> None:
        if not ctx.message.attachments:
            return await ctx.send("There was no image to use! Try using that command again with an image")
        async with aiohttp.ClientSession() as session:
            async with session.get(ctx.message.attachments[0].url) as r:
                if r.status == 200:
                    data = await r.read()
                    await self.bot.user.edit(avatar=data)
                    return await ctx.send("Set avatar, how do i look? 😏")
        await ctx.send("Failed to set avatar 😔")

    @set_avatar.error
    async def avatar_error(self, error, ctx) -> None:
        if isinstance(error, CommandCheckFailure):
            await ctx.send("You do not have permission to use this command!")

    @slash_command("stats", description="Get some stats about the bot")
    async def stats(self, ctx: InteractionContext) -> None:
        await ctx.defer()
        embed = Embed("Inquiry Stats", color=BrandColors.BLURPLE)

        async with self.bot.poll_cache.db.acquire() as conn:
            total_polls = await conn.fetchval("SELECT COUNT(*) FROM polls.poll_data WHERE guild_id = $1", ctx.guild.id)

            user_polls = await conn.fetchval("SELECT COUNT(*) FROM polls.poll_data WHERE author_id = $1", ctx.author.id)

        embed.add_field(name="Guilds", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Cached Users", value=str(len(self.bot.cache.user_cache)), inline=True)
        embed.add_field(name="Approx Users", value=f"{sum(g.member_count for g in self.bot.guilds):,}", inline=True)
        embed.add_field(name="Cached Polls", value=str(len(self.bot.poll_cache.polls)), inline=True)
        embed.add_field(name="Total Polls", value=str(await self.bot.poll_cache.get_total_polls()), inline=True)
        embed.add_field(name="Polls From This Guild", value=str(total_polls), inline=True)
        embed.add_field(name="Polls From You", value=str(user_polls), inline=True)
        embed.add_field(name="Scheduled Tasks", value=str(len(self.bot.scheduler.get_jobs())), inline=True)
        embed.add_field(
            name="Startup Time",
            value=Timestamp.fromdatetime(self.bot.start_time).format(TimestampStyles.RelativeTime),
            inline=True,
        )
        embed.add_field(
            name="NAFF version",
            value=f"[{naff.const.__version__}](https://github.com/NAFTeam/NAFF/commit/{self.naff_commit})",
            inline=True,
        )
        embed.add_field(
            name="Inquiry Commit",
            value=f"[{self.inquiry_commit}](https://github.com/LordOfPolls/Inquiry/commit/{self.inquiry_commit})",
            inline=True,
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        await ctx.send(embed=embed)


def setup(bot) -> None:
    Admin(bot)
