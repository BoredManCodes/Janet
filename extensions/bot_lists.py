import datetime
import logging
import os

import aiohttp
from naff import (
    Extension,
    Task,
    IntervalTrigger,
    InteractionContext,
    slash_command,
    listen,
    Embed,
    Button,
    ButtonStyles,
)

from models.events import PollCreate

log = logging.getLogger("Inquiry")


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
            await ctx.send("Voting has been temporarily disabled", ephemeral=True)

    async def has_voted(self, user_id: int) -> bool:
        data = await self.bot.poll_cache.get_user(user_id)
        if data:
            # if last_vote within the last 7 days
            if data["last_vote"] and (datetime.datetime.now() - data["last_vote"]).days < 7:
                return True
            return False

        # fallback to REST
        async with aiohttp.ClientSession(headers={"Authorization": self.top_gg_token}) as session:
            resp = await session.get(f"https://top.gg/api/bots/{self.bot.app.id}/check?userId={user_id}")
            if resp.status == 200:
                data = await resp.json()
                log.debug(f"Polled vote state for {user_id} over REST: {data}")
                if data["voted"] == 1:
                    await self.bot.poll_cache.set_user(user_id, datetime.datetime.now())
                    return True
                else:
                    await self.bot.poll_cache.set_user(user_id, None)
                    return False
            else:
                log.warning(f"Failed to check top.gg vote status: {resp.status} {resp.reason}")
                return True

    @listen("on_poll_create")
    async def vote_beg(self, event: PollCreate):
        if self.top_gg_token:
            if (datetime.datetime.now(datetime.timezone.utc) - event.ctx.guild.me.joined_at).days < 5:
                # if the bot joined less than 5 days ago, don't pester for votes
                return

            if not await self.has_voted(event.poll.author_id):
                embed = Embed(
                    "We all hate vote begging, but...",
                    description="Votes help keep the bot alive and growing; and it looks like you can vote for the bot right now!",
                    color=0xD23358,
                )
                embed.set_footer(
                    "Inquiry will never restrict features based on votes - voting will disable this message for 7 days."
                )
                button = Button(
                    ButtonStyles.LINK,
                    label="Vote",
                    url="https://top.gg/bot/{}/vote".format(self.bot.app.id),
                    emoji="<a:top_gg_spin:1041471838108258324>",
                )
                await event.ctx.send(embed=embed, components=button, ephemeral=True)


def setup(bot):
    BotLists(bot)
