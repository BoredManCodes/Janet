import asyncio
import datetime
import logging
import random
import time
from copy import deepcopy
from typing import Any

from naff import (
    Client,
    Intents,
    listen,
    MISSING,
    ComponentContext,
    Snowflake_Type,
    IntervalTrigger,
    Task,
    Modal,
    ShortText,
    CommandTypes,
    InteractionContext,
)
from naff.api.events import Button, MessageReactionAdd, ModalResponse
from naff.client.errors import NotFound
from naff.models.naff.application_commands import context_menu, slash_command

from models.poll import PollData
from poll_cache import PollCache

__all__ = ("Bot",)

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger("Inquiry")


class Bot(Client):
    def __init__(self) -> None:
        super().__init__(
            intents=Intents.new(guilds=True, reactions=True, default=False),
            sync_interactions=True,
            delete_unused_application_cmds=False,
            activity="with polls",
        )
        self.poll_cache: PollCache = MISSING

        self.polls_to_update: dict[Snowflake_Type, set[Snowflake_Type]] = {}

        self.update_lock = asyncio.Lock()  # prevent concurrent updates

    @classmethod
    async def run(cls, token: str) -> None:
        bot = cls()

        bot.load_extension("extensions.create_poll")
        bot.load_extension("extensions.edit_poll")
        bot.load_extension("extensions.poll_utils")
        bot.load_extension("extensions.admin")
        bot.load_extension("extensions.bot_lists")
        bot.load_extension("extensions.help")
        bot.load_extension("extensions.analytics")

        bot.poll_cache = await PollCache.initialize(bot)

        bot.__update_polls.start()
        bot.__cleanup_polls.start()

        await bot.astart(token)

    async def set_poll(self, guild_id: Snowflake_Type, message_id: Snowflake_Type, poll: PollData) -> None:
        await self.poll_cache.store_poll(guild_id, message_id, poll)

    @listen()
    async def on_startup(self) -> Any:
        await self.poll_cache.ready.wait()
        log.info(f"Logged in as {self.user.username}")
        log.info(f"Currently in {len(self.guilds)} guilds")

    @slash_command("invite", description="Get the invite link for this bot")
    async def invite(self, ctx: InteractionContext):
        await ctx.send(
            f"https://discord.com/api/oauth2/authorize?client_id={self.app.id}&permissions=377957124096&scope=bot%20applications.commands"
        )

    @slash_command("feedback", description="Send feedback to the bot owner")
    async def feedback(self, ctx: InteractionContext):
        await ctx.send("Thank you!\nhttps://forms.gle/6NDMJQXqmWL8fQVm6")

    @listen()
    async def on_modal_response(self, event: ModalResponse) -> Any:
        ctx = event.context
        ids = ctx.custom_id.split("|")
        if len(ids) == 2:
            await ctx.defer(ephemeral=True)

            message_id = ctx.custom_id.split("|")[1]
            if poll := await self.poll_cache.get_poll(ctx.guild_id, message_id):
                async with poll.lock:
                    poll.add_option(ctx.responses["new_option"])

                    if ctx.guild.id not in self.polls_to_update:
                        self.polls_to_update[ctx.guild.id] = set()
                    self.polls_to_update[ctx.guild.id].add(int(message_id))
                return await ctx.send(f"Added {ctx.responses['new_option']} to the poll")
            return await ctx.send("That poll could not be edited")

    @listen()
    async def on_button(self, event: Button) -> Any:
        ctx: ComponentContext = event.context
        if ctx.custom_id == "add_option":
            if await self.poll_cache.get_poll(ctx.guild_id, ctx.message.id):
                return await ctx.send_modal(
                    Modal(
                        "Add Option",
                        [ShortText(label="Option", custom_id="new_option")],
                        custom_id="add_option_modal|{}".format(ctx.message.id),
                    )
                )
            else:
                return await ctx.send("Cannot add options to that poll", ephemeral=True)
        else:
            await ctx.defer(ephemeral=True)

            option_index = int(ctx.custom_id.removeprefix("poll_option|"))

            if poll := await self.poll_cache.get_poll(ctx.guild.id, ctx.message.id):
                async with poll.lock:
                    if not poll.expired:
                        opt = poll.poll_options[option_index]
                        if poll.single_vote:
                            for _o in poll.poll_options:
                                if _o != opt:
                                    if ctx.author.id in _o.voters:
                                        _o.voters.remove(ctx.author.id)
                        if opt.vote(ctx.author.id):
                            await ctx.send(f"⬆️ Your vote for {opt.emoji}`{opt.inline_text}` has been added!")
                        else:
                            await ctx.send(f"⬇️ Your vote for {opt.emoji}`{opt.inline_text}` has been removed!")

                    if ctx.guild.id not in self.polls_to_update:
                        self.polls_to_update[ctx.guild.id] = set()
                    self.polls_to_update[ctx.guild.id].add(poll.message_id)
            else:
                await ctx.send("That poll could not be edited 😕")

    @listen()
    async def on_message_reaction_add(self, event: MessageReactionAdd) -> None:
        if event.emoji.name == "🔴":
            poll = await self.poll_cache.get_poll(event.message._guild_id, event.message.id)
            if poll:
                async with poll.lock:
                    if event.author.id == poll.author_id:
                        poll._expired = True
                        poll.closed = True
                        poll.expire_time = datetime.datetime.now()

                        await event.message.edit(embeds=poll.embed, components=poll.components)

                        await self.poll_cache.store_poll(event.message._guild_id, event.message.id, poll)

    @Task.create(IntervalTrigger(seconds=5))
    async def __update_polls(self) -> None:
        # messages edits have a 5-second rate limit, while technically you can edit a message multiple times within those 5 seconds
        # its a better idea to just over compensate and only edit once per 5 seconds
        tasks = []
        async with self.update_lock:
            polls = deepcopy(self.polls_to_update)

            if polls:
                for guild in polls:
                    for message_id in polls[guild]:
                        try:
                            poll = await self.poll_cache.get_poll_by_message(message_id)
                            if not poll.expired:
                                try:
                                    msg = await self.cache.fetch_message(poll.channel_id, poll.message_id)
                                except NotFound:
                                    log.warning(f"Poll {poll.message_id} not found - deleting from cache")
                                    await self.poll_cache.delete_poll(poll.channel_id, poll.message_id)
                                    continue
                                else:
                                    poll.reallocate_emoji()
                                    tasks.append(
                                        asyncio.create_task(msg.edit(embeds=poll.embed, components=poll.components))
                                    )
                                    tasks.append(self.poll_cache.store_poll(poll.guild_id, poll.message_id, poll))

                                finally:
                                    self.polls_to_update[guild].remove(message_id)
                                log.debug(f"Updated poll {poll.message_id}")
                        except Exception as e:
                            log.error(f"Error updating poll {message_id}", exc_info=e)
            await asyncio.gather(*tasks)

    @Task.create(IntervalTrigger(seconds=60))
    async def __cleanup_polls(self) -> None:
        tasks = []
        async with self.update_lock:
            for poll in self.poll_cache.polls.copy():
                try:
                    if poll.expired and not poll.closed:
                        async with poll.lock:
                            try:
                                msg = await self.cache.fetch_message(poll.channel_id, poll.message_id)
                            except NotFound:
                                log.warning(f"Poll {poll.message_id} not found - deleting from cache")
                                await self.poll_cache.delete_poll(poll.channel_id, poll.message_id)
                                continue
                            else:
                                tasks.append(msg.edit(embeds=poll.embed, components=[]))
                                poll.closed = True
                                tasks.append(self.poll_cache.store_poll(poll.guild_id, poll.message_id, poll))

                                log.debug(f"Poll {poll.message_id} expired - closed")
                except Exception as e:
                    log.error(f"Error cleaning up poll {poll.message_id}", exc_info=e)
            await asyncio.gather(*tasks)

    @context_menu("stress poll", CommandTypes.MESSAGE, scopes=[985991455074050078])
    async def __stress_poll(self, ctx: ComponentContext) -> None:
        # stresses out the poll system by voting a huge amount on a poll
        # this is a stress test for the system, and should not be used in production
        poll = await self.poll_cache.get_poll(ctx.guild_id, ctx.target.id)
        votes_per_cycle = 30000
        cycles = 10

        if poll:
            msg = await ctx.send("Stress testing...")

            for i in range(cycles):
                start = time.perf_counter()
                for _ in range(votes_per_cycle):
                    async with poll.lock:
                        opt = random.choice(poll.poll_options)
                        voter = random.randrange(1, 10**11)
                        if not poll.expired:
                            if poll.single_vote:
                                for _o in poll.poll_options:
                                    if _o != opt:
                                        if voter in _o.voters:
                                            _o.voters.remove(voter)
                            opt.vote(voter)
                            if ctx.guild.id not in self.polls_to_update:
                                self.polls_to_update[ctx.guild.id] = set()
                            self.polls_to_update[ctx.guild.id].add(poll.message_id)

                end = time.perf_counter()

                await asyncio.sleep(2 - (end - start))
                await msg.edit(
                    content=f"Stress testing... {i+1}/{cycles} ({votes_per_cycle:,} votes per cycle) @ {round(votes_per_cycle / (end - start)):,} votes per second"
                )
            await msg.edit(
                content=f"Stress Completed... {i+1}/{cycles} ({votes_per_cycle:,} votes per cycle) @ {round(votes_per_cycle / (end - start)):,} votes per second"
            )

        else:
            await ctx.send("That poll could not be found")


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    token = os.getenv("TOKEN")
    asyncio.run(Bot.run(token))
