import asyncio
import logging
from copy import deepcopy
from dataclasses import MISSING
from pathlib import Path
from typing import Optional

import aioredis
import dis_snek
import orjson
from dis_snek import Modal, ShortText, ParagraphText, IntervalTrigger, Task
from dis_snek.api.events import MessageReactionAdd
from dis_snek.client import Snake
from dis_snek.models import (
    slash_command,
    InteractionContext,
    OptionTypes,
    Snowflake_Type,
    ComponentContext,
    listen,
    SlashCommandOption,
    AutocompleteContext,
    to_snowflake,
    SlashCommandChoice,
    MaterialColors,
    Timestamp,
    Permissions,
)
from thefuzz import fuzz

from models.emoji import booleanEmoji
from models.poll import PollData, PollOption

logging.basicConfig()
log = logging.getLogger("Inquiry")
cls_log = logging.getLogger(dis_snek.const.logger_name)
cls_log.setLevel(logging.DEBUG)
log.setLevel(logging.DEBUG)

colours = sorted(
    [MaterialColors(c).name.title() for c in MaterialColors]
    + [
        "Blurple",
        "Fuchsia",
        "White",
        "Black",
    ]
)

def_options = [
    SlashCommandOption(
        "title", OptionTypes.STRING, "The title for your poll", required=True
    ),
    SlashCommandOption(
        "single_vote",
        OptionTypes.BOOLEAN,
        "Only allow a single vote per user (default False)",
        required=False,
    ),
    SlashCommandOption(
        "channel",
        OptionTypes.CHANNEL,
        "The channel to send your poll to, if not the current channel",
        required=False,
    ),
    SlashCommandOption(
        "duration",
        OptionTypes.INTEGER,
        "Automatically close the poll after this many minutes",
        required=False,
    ),
    SlashCommandOption(
        "inline",
        OptionTypes.BOOLEAN,
        "Make options appear inline, in the embed (default True)",
        required=False,
    ),
    SlashCommandOption(
        "colour",
        OptionTypes.STRING,
        "Choose the colour of the embed (default 'blurple')",
        choices=[SlashCommandChoice(c.replace("_", " "), c) for c in colours],
        required=False,
    ),
]


class Bot(Snake):
    def __init__(self):
        super().__init__(
            sync_interactions=True,
            asyncio_debug=True,
            delete_unused_application_cmds=True,
            activity="with polls",
            debug_scope=707631108753195008,
        )
        self.polls: dict[Snowflake_Type, dict[Snowflake_Type, PollData]] = {}
        self.polls_to_update: dict[Snowflake_Type, set[Snowflake_Type]] = {}

        self.redis: aioredis.Redis = MISSING

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
        keys = await self.redis.keys("*")
        for key in keys:
            poll_data = await self.redis.get(key)
            try:
                poll = PollData(**orjson.loads(poll_data))

                guild_id, msg_id = [to_snowflake(k) for k in key.split("|")]
                author = await self.cache.fetch_member(guild_id, poll.author_id)
                poll.author_data = {
                    "name": author.display_name,
                    "avatar_url": author.avatar.url,
                }

                if not self.polls.get(guild_id):
                    self.polls[guild_id] = {}
                self.polls[guild_id][msg_id] = poll
            except TypeError:
                continue

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

    @slash_command(
        "poll",
        "Create a poll",
        options=def_options,
    )
    async def poll(self, ctx: InteractionContext, **kwargs):
        modal = Modal(
            "Create a poll!",
            components=[
                ParagraphText(
                    "Options: ",
                    placeholder="Start each option with a `-` ie: \n-Option 1\n-Option 2",
                    custom_id="options",
                )
            ],
        )
        await ctx.send_modal(modal)

        m_ctx = await self.wait_for_modal(modal, ctx.author)
        if not m_ctx.kwargs["options"].strip():
            return await m_ctx.send("You did not provide any options!", ephemeral=True)

        poll = PollData.from_ctx(ctx, m_ctx)

        msg = await poll.send(await self.cache.fetch_channel(poll.channel_id))
        await self.set_poll(ctx.guild_id, msg.id, poll)
        await m_ctx.send("To close the poll, react to it with 🔴", ephemeral=True)

    @slash_command(
        "poll_prefab",
        "Create a poll using pre-set options",
        sub_cmd_name="boolean",
        sub_cmd_description="A poll with yes and no options",
        options=def_options,
    )
    async def boolean(self, ctx: InteractionContext, **kwargs):
        await ctx.defer(ephemeral=True)
        if channel := kwargs.get("channel"):
            u_perms = ctx.author.channel_permissions(channel)
            if Permissions.SEND_MESSAGES not in u_perms:
                return await ctx.send(
                    f"You do not have permission to send messages in {channel.mention}"
                )

        poll = PollData.from_ctx(ctx)
        poll.poll_options.append(PollOption("Yes", booleanEmoji[0]))
        poll.poll_options.append(PollOption("No", booleanEmoji[1]))

        msg = await poll.send(await self.cache.fetch_channel(poll.channel_id))
        await self.set_poll(ctx.guild_id, msg.id, poll)
        await ctx.send("To close the poll, react to it with 🔴")

    @boolean.subcommand(
        sub_cmd_name="week",
        sub_cmd_description="A poll with options for each day of the week",
        options=def_options,
    )
    async def week(self, ctx: InteractionContext, **kwargs):
        await ctx.defer(ephemeral=True)
        poll = PollData.from_ctx(ctx)
        options = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        for opt in options:
            poll.add_option(opt)

        msg = await poll.send(ctx)
        await self.set_poll(ctx.guild_id, msg.id, poll)
        await ctx.send("To close the poll, react to it with 🔴")

    @slash_command(
        "edit_poll",
        "edit a given poll",
        sub_cmd_name="remove_option",
        sub_cmd_description="Remove an option from the poll",
        options=[
            SlashCommandOption(
                name="poll",
                description="The poll to edit",
                type=OptionTypes.STRING,
                required=True,
                autocomplete=True,
            ),
            SlashCommandOption(
                name="option",
                description="The option to remove",
                type=OptionTypes.STRING,
                required=True,
                autocomplete=True,
            ),
        ],
    )
    async def edit_poll_remove(self, ctx: InteractionContext, poll, option):
        await ctx.defer(ephemeral=True)

        if poll := await self.process_poll_option(ctx, poll):
            if poll.author_id == ctx.author.id:
                message = await self.cache.get_message(poll.channel_id, poll.message_id)
                if message:
                    async with poll.lock:
                        for i in range(len(poll.poll_options)):
                            if poll.poll_options[i].text == option.replace("_", " "):
                                del poll.poll_options[i]
                                await message.edit(
                                    embeds=poll.embed, components=poll.components
                                )
                                await ctx.send(
                                    f"Removed `{option}` from `{poll.title}`"
                                )
                                break
                        else:
                            await ctx.send(
                                f"Failed to remove `{option}` from `{poll.title}`"
                            )
                    return
            else:
                return await ctx.send("Only the author of the poll can edit it!")

    @edit_poll_remove.subcommand(
        sub_cmd_name="add_option",
        sub_cmd_description="Add an option to the poll",
        options=[
            SlashCommandOption(
                name="poll",
                description="The poll to edit",
                type=OptionTypes.STRING,
                required=True,
                autocomplete=True,
            ),
            SlashCommandOption(
                name="option",
                description="The option to add",
                type=OptionTypes.STRING,
                required=True,
            ),
        ],
    )
    async def edit_poll_add(self, ctx: InteractionContext, poll, option):
        await ctx.defer(ephemeral=True)

        if poll := await self.process_poll_option(ctx, poll):
            if poll.author_id == ctx.author.id:

                message = await self.cache.get_message(poll.channel_id, poll.message_id)
                if message:
                    async with poll.lock:
                        poll.add_option(option)
                        await message.edit(
                            embeds=poll.embed, components=poll.components
                        )
                        await ctx.send(f"Added `{option}` to `{poll.title}`")
                    return
            else:
                await ctx.send("Only the author of the poll can edit it!")

    @edit_poll_remove.autocomplete("poll")
    @edit_poll_add.autocomplete("poll")
    async def poll_autocomplete(self, ctx: AutocompleteContext, **kwargs):
        polls = self.polls.get(ctx.guild_id)
        if polls:
            polls = [
                p
                for p in polls.values()
                if p.author_id == ctx.author.id and not p.expired
            ]
            polls = sorted(
                polls,
                key=lambda x: fuzz.partial_ratio(x.title, ctx.input_text),
                reverse=True,
            )[:25]

            await ctx.send(
                [
                    {
                        "name": f"{p.title} ({Timestamp.from_snowflake(p.message_id).ctime()})",
                        "value": str(p.message_id),
                    }
                    for p in polls
                ]
            )

        else:
            await ctx.send([])

    @edit_poll_remove.autocomplete("option")
    async def option_autocomplete(self, ctx: AutocompleteContext, **kwargs):
        poll = await self.get_poll(ctx.guild_id, to_snowflake(kwargs.get("poll")))
        if poll:
            p_options = list(poll.poll_options)
            p_options = sorted(
                p_options,
                key=lambda x: fuzz.partial_ratio(x.text, ctx.input_text),
                reverse=True,
            )[:25]

            await ctx.send([p.text for p in p_options])

        else:
            await ctx.send([])

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

    @slash_command("invite", "Invite Inquiry to your server!")
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
                    msg = await self.cache.get_message(poll.channel_id, poll.message_id)
                    if msg:
                        await msg.edit(embeds=poll.embed, components=[])

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
                            msg = await self.cache.fetch_message(
                                poll.channel_id, poll.message_id
                            )
                            if msg:
                                await msg.edit(
                                    embeds=poll.embed, components=poll.components
                                )
                        self.polls_to_update[guild].remove(poll_id)
                    await asyncio.sleep(0)


bot = Bot()

bot.grow_scale("scales.admin")

bot.start((Path(__file__).parent / "token.txt").read_text().strip())
