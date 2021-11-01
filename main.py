import asyncio
from pathlib import Path
from typing import Optional

import aioredis
import orjson
from dis_snek.client import Snake
from dis_snek.const import MISSING
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
)
from dis_snek.models.events import MessageReactionAdd
from thefuzz import fuzz

from models.poll import PollData, PollOption

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
        OptionTypes.NUMBER,
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
            sync_interactions=False,
            asyncio_debug=False,
            delete_unused_application_cmds=True,
            activity="with polls",
        )
        self.polls: dict[Snowflake_Type, dict[Snowflake_Type, PollData]] = {}

        self.redis: aioredis.Redis = MISSING

    @listen()
    async def on_ready(self):
        print("Connected to discord!")

        try:
            await self.connect()
            print("Connected to redis!") if await self.redis.ping() else exit()
        except aioredis.exceptions.ConnectionError:
            print("Failed to connect to redis, aborting login")
            return await self.stop()

        await self.cache_polls()
        print(f"{self.total_polls} polls cached")

        asyncio.create_task(self.task_loop())

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
        try:
            self.polls[guild_id].pop(msg_id)
        except:
            breakpoint()

        await self.redis.delete(f"{guild_id}|{msg_id}")

    @slash_command(
        "poll",
        "Create a poll",
        options=[
            SlashCommandOption(
                "options",
                OptionTypes.STRING,
                "The options for your poll, seperated by commas",
                required=True,
            ),
        ]
        + def_options,
    )
    async def poll(self, ctx: InteractionContext, **kwargs):
        poll = PollData.from_ctx(ctx)

        msg = await poll.send(ctx)
        await self.set_poll(ctx.guild_id, msg.id, poll)

    @slash_command(
        "poll_prefab",
        "Create a poll using pre-set options",
        sub_cmd_name="boolean",
        sub_cmd_description="A poll with yes and no options",
        options=def_options,
    )
    async def boolean(self, ctx: InteractionContext, **kwargs):
        poll = PollData.from_ctx(ctx)
        poll.poll_options.append(PollOption("Yes", "✅"))
        poll.poll_options.append(PollOption("No", "❌"))

        msg = await poll.send(ctx)
        await self.set_poll(ctx.guild_id, msg.id, poll)

    @boolean.subcommand(
        sub_cmd_name="week",
        sub_cmd_description="A poll with options for each day of the week",
        options=def_options,
    )
    async def week(self, ctx: InteractionContext, **kwargs):
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
        poll = await self.get_poll(ctx.guild_id, to_snowflake(poll))
        if poll:
            if poll.author_id == ctx.author.id:
                message = await self.cache.get_message(poll.channel_id, poll.message_id)
                if message:
                    async with poll.lock:
                        for i in range(len(poll.poll_options)):
                            if poll.poll_options[i].text == option:
                                del poll.poll_options[i]
                                break
                        else:
                            return await ctx.send(
                                f"Failed to remove`{option}` from `{poll.title}`"
                            )
                        await message.edit(
                            embeds=poll.embed, components=poll.components
                        )
                        return await ctx.send(f"Removed `{option}` from `{poll.title}`")
                await ctx.send("Failed to edit poll!")
            else:
                await ctx.send("Only the author of the poll can edit it!")

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
        poll = await self.get_poll(ctx.guild_id, to_snowflake(poll))
        if poll:
            if poll.author_id == ctx.author.id:

                message = await self.cache.get_message(poll.channel_id, poll.message_id)
                if message:
                    async with poll.lock:
                        poll.add_option(option)
                        await message.edit(
                            embeds=poll.embed, components=poll.components
                        )
                        return await ctx.send(f"Added `{option}` to `{poll.title}`")
                await ctx.send("Failed to edit poll!")
            else:
                await ctx.send("Only the author of the poll can edit it!")

    @edit_poll_remove.autocomplete("poll")
    @edit_poll_add.autocomplete("poll")
    async def poll_autocomplete(self, ctx: AutocompleteContext, **kwargs):
        polls = self.polls.get(ctx.guild_id)
        if polls:
            polls = [p for p in polls.values() if not p.expired]
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
        await ctx.defer(edit_origin=True)

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
                    opt.vote(ctx.author.id)
                await poll.send(ctx)
                await self.set_poll(ctx.guild_id, ctx.message.id, poll)

    @listen()
    async def on_message_reaction_add(self, event: MessageReactionAdd):
        if event.emoji.name == "🔴":
            poll = await self.get_poll(event.message._guild_id, event.message.id)
            if poll:
                async with poll.lock:
                    if event.author.id == poll.author_id:
                        poll._expired = True
                        await event.message.edit(embeds=poll.embed, components=[])
                    await self.delete_poll(event.message._guild_id, event.message.id)

    @slash_command("invite", "Invite Inquiry to your server!")
    async def invite(self, ctx: InteractionContext):
        await ctx.send(
            f"https://discord.com/oauth2/authorize?client_id={self.user.id}&scope=applications.commands%20bot",
            ephemeral=True,
        )

    async def close_polls(self):
        polls = self.polls.copy()
        polls_to_close = {}

        for guild in polls.keys():
            for poll in polls[guild].values():
                if poll.expired:
                    print("Poll needs closing")
                    if guild not in polls_to_close:
                        polls_to_close[guild] = []
                    polls_to_close[guild].append(poll)

        for k, polls in polls_to_close.items():
            for poll in polls:
                print(f"Closing poll: {poll.message_id}")
                msg = await self.cache.get_message(poll.channel_id, poll.message_id)
                if msg:
                    await msg.edit(embeds=poll.embed, components=[])

                await self.delete_poll(k, poll.message_id)

    async def task_loop(self):
        while not self.is_closed:
            await asyncio.gather(asyncio.sleep(30), self.close_polls())


bot = Bot()

bot.grow_scale("scales.admin")

bot.start((Path(__file__).parent / "token.txt").read_text().strip())
