import logging
import os

import aiohttp
from naff import Extension, Task, IntervalTrigger

log = logging.getLogger("bot-lists")


class BotLists(Extension):
    def __init__(self, *args, **kwargs):
        self.discord_bots_gg_token = os.environ.get("DISCORD_BOTS_GG_TOKEN", None)

        if self.discord_bots_gg_token:
            self.discord_bots_gg.start()
        else:
            log.warning("No discord_bots_gg_token provided, not posting to discord.bots.gg")

    @Task.create(IntervalTrigger(minutes=1))
    async def discord_bots_gg(self) -> None:
        await self.bot.wait_until_ready()

        async with aiohttp.ClientSession(headers={"Authorization": self.discord_bots_gg_token}) as session:
            resp = await session.post(
                f"https://discord.bots.gg/api/v1/bots/{self.bot.user.id}/stats",
                json={
                    "guildCount": len(self.bot.guilds),
                    "shardCount": self.bot.total_shards,
                    "shardId": self.bot._connection_state.shard_id,  # noqa
                },
            )
            if resp.status == 200:
                log.debug("Posted stats to discord.bots.gg")
            else:
                log.warning(f"Failed to post stats to discord.bots.gg: {resp.status} {resp.reason}")


def setup(bot):
    BotLists(bot)
