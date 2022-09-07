import subprocess
from typing import TYPE_CHECKING

import aiohttp
import naff
from naff.client.errors import CommandCheckFailure
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

        # get commit hash
        git_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"]).decode("ascii").strip()

        embed.add_field(name="Guilds", value=str(len(self.bot.guilds)))
        embed.add_field(name="Cached Users", value=str(len(self.bot.cache.user_cache)))
        embed.add_field(name="Active Polls", value=str(len(self.bot.poll_cache.polls)))
        embed.add_field(name="Pending Updates", value=str(sum(len(v) for v in self.bot.polls_to_update.values())))
        embed.add_field(
            name="Startup Time", value=Timestamp.fromdatetime(self.bot.start_time).format(TimestampStyles.RelativeTime)
        )
        embed.add_field(
            name="NAFF version",
            value=f"[{naff.const.__version__}](https://github.com/NAFTeam/NAFF/releases/tag/NAFF-{naff.const.__version__})",
        )
        embed.add_field(
            name="Inquiry Commit", value=f"[{git_hash}](https://github.com/LordOfPolls/Inquiry/commit/{git_hash})"
        )
        embed.set_thumbnail(url=self.bot.user.avatar.url)
        await ctx.send(embed=embed)

    @slash_command("server", description="Join the support server")
    async def server(self, ctx: InteractionContext) -> None:
        await ctx.send("https://discord.gg/vtRTAwmQsH")


def setup(bot) -> None:
    Admin(bot)
