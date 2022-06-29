import asyncio
import logging
import re
from copy import deepcopy
from dataclasses import MISSING
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import aioredis
import naff
import orjson
from naff import (
    IntervalTrigger,
    Task,
    Intents,
)
from naff.api.events import MessageReactionAdd
from naff.client import Client
from naff.client.errors import NotFound
from naff.models import (
    slash_command,
    InteractionContext,
    Snowflake_Type,
    ComponentContext,
    listen,
    to_snowflake,
)

from models.poll import PollData

logging.basicConfig()
log = logging.getLogger("Inquiry")
cls_log = logging.getLogger(naff.const.logger_name)
cls_log.setLevel(logging.DEBUG)
log.setLevel(logging.DEBUG)


time_pattern = re.compile(r"(\d+\.?\d?[s|m|h|d|w]{1})\s?", re.I)


def process_duration(delay):
    units = {"w": "weeks", "d": "days", "h": "hours", "m": "minutes", "s": "seconds"}
    delta = {"weeks": 0, "days": 0, "hours": 0, "minutes": 0, "seconds": 0}
    # delay: str = ctx.kwargs.get("duration")
    if delay:
        if times := time_pattern.findall(delay):
            for t in times:
                delta[units[t[-1]]] += float(t[:-1])
        else:
            # await ctx.send(
            #     "Invalid time string, please follow example: `1w 3d 7h 5m 20s`",
            #     ephemeral=True,
            # )
            return False

        if not any(value for value in delta.items()):
            # await ctx.send("At least one time period is required", ephemeral=True)
            return False

        remind_at = datetime.now() + timedelta(**delta)
        return remind_at
    return delay


class Bot(Client):
    def __init__(self):
        super().__init__(
            intents=Intents.DEFAULT | Intents.GUILD_MEMBERS,
            sync_interactions=True,
            asyncio_debug=True,
            delete_unused_application_cmds=True,
            activity="with polls",
            fetch_members=True,
        )
        self.polls: dict[Snowflake_Type, dict[Snowflake_Type, PollData]] = {}
        self.polls_to_update: dict[Snowflake_Type, set[Snowflake_Type]] = {}

        self.redis: aioredis.Redis = MISSING

        self.load_extension("extensions.create_poll")
        self.load_extension("extensions.edit_poll")

    @listen()
    async def on_ready(self):
        log.debug("Connected to discord!")
        log.info(f"Logged in as {self.user.username}")
        log.debug(f"Currently in {len(self.guilds)} guilds")

        try:
            await self.connect()
            log.info("Connected to redis!") if await self.redis.ping() else exit()
        except aioredis.exceptions.ConnectionError:
            log.error("Failed to connect to redis, aborting login")
            return await self.stop()

        await self.cache_polls()
        log.debug(f"{self.total_polls} polls cached")

        self.update_polls.start()
        self.close_polls.start()

    @property
    def total_polls(self):
        total = 0
        for guild in self.polls.keys():
            for _ in self.polls[guild]:
                total += 1
        return total

    async def connect(self):
        self.redis = await aioredis.from_url(
            "redis://localhost/5", decode_responses=True
        )

    async def cache_polls(self):
        async def _cache_poll(_key):
            if _key:
                try:
                    poll_data = await self.redis.get(_key)

                    poll = PollData(**orjson.loads(poll_data))

                    guild_id, msg_id = [to_snowflake(k) for k in _key.split("|")]
                    try:
                        author = await self.cache.fetch_member(guild_id, poll.author_id)
                    except NotFound:
                        poll.author_data = {
                            "name": "Unknown",
                            "avatar_url": None,
                        }
                    else:
                        poll.author_data = {
                            "name": author.display_name,
                            "avatar_url": author.avatar.url,
                        }

                    if not self.polls.get(guild_id):
                        self.polls[guild_id] = {}
                    self.polls[guild_id][msg_id] = poll
                except (TypeError, ValueError):
                    return

        await asyncio.gather(*[_cache_poll(k) for k in await self.redis.keys("*")])

    async def get_poll(
        self, guild_id: Snowflake_Type, msg_id: Snowflake_Type
    ) -> Optional[PollData]:
        try:
            return self.polls[guild_id][msg_id]
        except KeyError:
            poll_data = await self.redis.get(f"{guild_id}|{msg_id}")
            if poll_data:
                poll = PollData(**orjson.loads(poll_data))

                if not self.polls.get(guild_id):
                    self.polls[guild_id] = {}
                self.polls[guild_id][msg_id] = poll

                return poll
        return None

    async def process_poll_option(self, ctx: InteractionContext, poll: str):
        try:
            poll = await self.get_poll(ctx.guild_id, to_snowflake(poll))
        except AttributeError:
            pass
        finally:
            if not isinstance(poll, PollData):
                await ctx.send("Unable to find the requested poll!")
                return None
            return poll

    async def set_poll(
        self, guild_id: Snowflake_Type, msg_id: Snowflake_Type, poll: PollData
    ):
        if not self.polls.get(guild_id):
            self.polls[guild_id] = {}
        self.polls[guild_id][msg_id] = poll
        await self.redis.set(
            f"{guild_id}|{poll.message_id}", orjson.dumps(poll.__dict__())
        )

    async def delete_poll(self, guild_id: Snowflake_Type, msg_id: Snowflake_Type):
        log.debug(f"Deleting poll: {guild_id}|{msg_id}")
        try:
            self.polls[guild_id].pop(msg_id)
        except:
            breakpoint()

        await self.redis.delete(f"{guild_id}|{msg_id}")

    @listen()
    async def on_button(self, event):
        ctx: ComponentContext = event.context
        await ctx.defer(ephemeral=True)

        opt_index = int(ctx.custom_id.removeprefix("poll_option|"))

        if poll := await self.get_poll(ctx.guild_id, ctx.message.id):
            async with poll.lock:
                if not poll.expired:
                    opt = poll.poll_options[opt_index]
                    if poll.single_vote:
                        for _o in poll.poll_options:
                            if _o != opt:
                                if ctx.author.id in _o.voters:
                                    _o.voters.remove(ctx.author.id)
                    if opt.vote(ctx.author.id):
                        await ctx.send(
                            f"⬆️ Your vote for {opt.emoji}`{opt.inline_text}` has been added!"
                        )
                    else:
                        await ctx.send(
                            f"⬇️ Your vote for {opt.emoji}`{opt.inline_text}` has been removed!"
                        )

                if ctx.guild_id not in self.polls_to_update:
                    self.polls_to_update[ctx.guild_id] = set()
                self.polls_to_update[ctx.guild_id].add(poll.message_id)
                await self.set_poll(ctx.guild_id, ctx.message.id, poll)
        else:
            await ctx.send("That poll could not be edited 😕")

    @listen()
    async def on_message_reaction_add(self, event: MessageReactionAdd):
        if event.emoji.name == "🔴":
            poll = await self.get_poll(event.message._guild_id, event.message.id)
            if poll:
                async with poll.lock:
                    if event.author.id == poll.author_id:
                        poll._expired = True
                        await event.message.edit(embeds=poll.embed, components=[])
                        await self.delete_poll(
                            event.message._guild_id, event.message.id
                        )

    @slash_command("invite", description="Invite Inquiry to your server!")
    async def invite(self, ctx: InteractionContext):
        await ctx.send(
            f"https://discord.com/oauth2/authorize?client_id={self.user.id}&scope=applications.commands%20bot",
            ephemeral=True,
        )

    @Task.create(IntervalTrigger(seconds=30))
    async def close_polls(self):
        polls = self.polls.copy()
        polls_to_close = {}

        for guild in polls.keys():
            for poll in polls[guild].values():
                if poll.expired:
                    log.debug("Poll needs closing")
                    if guild not in polls_to_close:
                        polls_to_close[guild] = []
                    polls_to_close[guild].append(poll)

        for k, polls in polls_to_close.items():
            for poll in polls:
                async with poll.lock:
                    log.debug(f"Closing poll: {poll.message_id}")
                    try:
                        msg = await self.cache.fetch_message(
                            poll.channel_id, poll.message_id
                        )
                    except NotFound:
                        log.warning(
                            f"Could not find message with {poll.message_id}, removing from cache"
                        )
                    else:
                        await msg.edit(embeds=poll.embed, components=[])
                    finally:
                        await self.delete_poll(k, poll.message_id)

    @Task.create(IntervalTrigger(seconds=2))
    async def update_polls(self):
        polls = deepcopy(self.polls_to_update)
        if polls:
            for guild in polls.keys():
                for poll_id in polls[guild]:
                    poll = await self.get_poll(guild, poll_id)
                    async with poll.lock:
                        if not poll.expired:
                            log.debug(f"updating {poll_id}")
                            try:
                                msg = await self.cache.fetch_message(
                                    poll.channel_id, poll.message_id
                                )
                            except NotFound:
                                log.warning(
                                    f"Could not find message with {poll.message_id}, aborting updates for this poll"
                                )
                            else:
                                await msg.edit(
                                    embeds=poll.embed, components=poll.components
                                )
                            finally:
                                try:
                                    self.polls_to_update[guild].remove(poll_id)
                                except KeyError:
                                    pass
                    await asyncio.sleep(0)


bot = Bot()

bot.load_extension("extensions.admin")

bot.start((Path(__file__).parent / "token.txt").read_text().strip())
