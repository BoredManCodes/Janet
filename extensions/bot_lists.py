import logging
import os

import aiohttp
from naff import Extension, Task, IntervalTrigger, InteractionContext, slash_command

log = logging.getLogger("bot-lists")


class BotLists(Extension):
    def __init__(self, *args, **kwargs):
        self.discord_bots_gg_token = os.environ.get("DISCORD_BOTS_GG_TOKEN", None)
        self.top_gg_token = os.environ.get("TOP_GG_TOKEN", None)

        if self.discord_bots_gg_token:
            self.discord_bots_gg.start()
        else:
            log.warning("No discord_bots_gg_token provided, not posting to discord.bots.gg")

        if self.top_gg_token:
            self.top_gg.start()
        else:
            log.warning("No top_gg_token provided, not posting to top.gg")

    @Task.create(IntervalTrigger(minutes=5))
    async def discord_bots_gg(self) -> None:
        await self.bot.wait_until_ready()

        async with aiohttp.ClientSession(headers={"Authorization": self.discord_bots_gg_token}) as session:
            resp = await session.post(
                f"https://discord.bots.gg/api/v1/bots/{self.bot.user.id}/stats",
                json={
                    "guildCount": len(self.bot.guilds),
                },
            )
            if resp.status == 200:
                log.debug("Posted stats to discord.bots.gg")
            else:
                log.warning(f"Failed to post stats to discord.bots.gg: {resp.status} {resp.reason}")

    @Task.create(IntervalTrigger(minutes=5))
    async def top_gg(self) -> None:
        await self.bot.wait_until_ready()

        async with aiohttp.ClientSession(headers={"Authorization": self.top_gg_token}) as session:
            resp = await session.post(
                f"https://top.gg/api/bots/{self.bot.app.id}/stats",
                json={
                    "server_count": len(self.bot.guilds),
                },
            )
            if resp.status == 200:
                log.debug("Posted stats to top.gg")
            else:
                log.warning(f"Failed to post stats to top.gg: {resp.status} {resp.reason}")

    @slash_command("vote", description="Vote for the bot on top.gg")
    async def top_gg_vote(self, ctx: InteractionContext):
        if self.top_gg_token:
            await ctx.send(
                "Thanks for voting! You won't get anything, but it helps the bot grow!\n\nhttps://top.gg/bot/{}/vote".format(
                    self.bot.app.id
                )
            )
        else:
            await ctx.send("Voting has been temporarily disabled pending verification from Discord", ephemeral=True)


def setup(bot):
    BotLists(bot)
