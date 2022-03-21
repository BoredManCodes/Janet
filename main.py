import asyncio
import inspect
import json
import logging
import os
import sys
import traceback
from configparser import RawConfigParser
from copy import deepcopy
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp
import aioredis
import dis_snek
import orjson
from dis_snek.client import Snake
from dis_snek import MISSING, Intents, check, AutoDefer, Embed, Context, Modal, MessageContext, CMD_BODY
from dis_snek.models import (
    slash_command,
    InteractionContext,
    OptionTypes,
    Snowflake_Type,
    ComponentContext,
    listen,
    AutocompleteContext,
    to_snowflake,
    SlashCommandChoice,
    MaterialColors,
    Timestamp,
    Permissions,
)
from dis_snek.models.snek.application_commands import SlashCommandOption, slash_option
from dis_snek.api.events import MessageReactionAdd
from dis_snek import Task
from dis_snek.models.snek.tasks.triggers import IntervalTrigger
from dis_snek.models.discord import color
from thefuzz import fuzz
from models.emoji import booleanEmoji
from models.poll import PollData, PollOption
from pastypy import AsyncPaste as Paste

logging.basicConfig()
log = logging.getLogger("Inquiry")
cls_log = logging.getLogger(dis_snek.const.logger_name)
cls_log.setLevel(logging.INFO)
log.setLevel(logging.INFO)
if os.path.isfile("config.ini"):
    log.info("Config found")
else:
    log.error("Config not found")
    exit(1)
Config = RawConfigParser()
Config.read("config.ini")
colours = sorted(
    [MaterialColors(c).name.title() for c in MaterialColors]
    + [
        "Blurple",
        "Fuchsia",
        "White",
        "Black",
    ]
)


def ConfigSectionMap(section):
    dict1 = {}
    options = Config.options(section)
    for option in options:
        try:
            dict1[option] = Config.get(section, option)
            if dict1[option] == -1:
                log.info("skip: %s" % option)
        except:
            log.exception("exception on %s!" % option)
            dict1[option] = None
    return dict1
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
ERROR_MSG = """
Command Information:
  Name: {invoked_name}
  Args:
{arg_str}

Callback:
  Args:
{callback_args}
  Kwargs:
{callback_kwargs}
"""


class Bot(Snake):
    def __init__(self):
        super().__init__(
            sync_interactions=True,
            asyncio_debug=False,
            delete_unused_application_cmds=False,
            activity="Development",
            default_prefix="$",
            debug_scope=891613945356492890,
            intents=Intents.DEFAULT | Intents.GUILD_MEMBERS,
            fetch_members=True,
            auto_defer=AutoDefer(enabled=True, time_until_defer=.1)
        )
        self.polls: dict[Snowflake_Type, dict[Snowflake_Type, PollData]] = {}
        self.polls_to_update: dict[Snowflake_Type, set[Snowflake_Type]] = {}
        self.redis: aioredis.Redis = MISSING
        self.available: asyncio.Event = asyncio.Event()
        self.available.set()

    @listen()
    async def on_ready(self):
        log.info("Connected to discord!")
        log.info(f"Logged in as {self.user.username}")
        log.info(f"Currently in {len(self.guilds)} guilds")
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

    async def on_command_error(
            self, ctx: Context, error: Exception, *args: list, **kwargs: dict
    ) -> None:
        """Lepton on_command_error override."""
        guild = await self.fetch_guild(891613945356492890)
        channel = await guild.fetch_channel(940919818561912872)
        error_time = datetime.utcnow().strftime("%d-%m-%Y %H:%M-%S.%f UTC")
        timestamp = int(datetime.now().timestamp())
        timestamp = f"<t:{timestamp}:T>"
        arg_str = (
            "\n".join(f"    {k}: {v}" for k, v in ctx.kwargs.items()) if ctx.kwargs else "    None"
        )
        callback_args = "\n".join(f"    - {i}" for i in args) if args else "    None"
        callback_kwargs = (
            "\n".join(f"    {k}: {v}" for k, v in kwargs.items()) if kwargs else "    None"
        )
        full_message = ERROR_MSG.format(
            error_time=error_time,
            invoked_name=ctx.invoked_name,
            arg_str=arg_str,
            callback_args=callback_args,
            callback_kwargs=callback_kwargs,
        )
        if len(full_message) >= 1900:
            error_message = "  ".join(traceback.format_exception(error))
            full_message += "Exception: |\n  " + error_message
            paste = Paste(content=full_message)
            await paste.save("https://paste.trent-buckley.com")

            await channel.send(
                f"Janet encountered an error at {timestamp}. Log was too big to send over Discord."
                f"\nPlease see log at {paste.url}"
            )
        else:
            error_message = "".join(traceback.format_exception(error))
            await channel.send(
                f"Janet encountered an error at {timestamp}:"
                f"\n```yaml\n{full_message}\n```"
                f"\nException:\n```py\n{error_message}\n```"
            )
        await ctx.send("Whoops! Encountered an error. The error has been logged.", ephemeral=True)
        return await super().on_command_error(ctx, error, *args, **kwargs)

    @property
    def total_polls(self):
        total = 0
        for guild in self.polls.keys():
            for _ in self.polls[guild]:
                total += 1
        return total

    async def connect(self):
        self.redis = await aioredis.from_url(
            ConfigSectionMap("DatabaseSettings")["host"],
            username=ConfigSectionMap("DatabaseSettings")["username"],
            password=ConfigSectionMap("DatabaseSettings")["password"],
            decode_responses=True
        )

    async def cache_polls(self):
        keys = await self.redis.keys("*")
        for key in keys:
            poll_data = await self.redis.get(key)
            try:
                poll = PollData(**orjson.loads(poll_data))

                guild_id, msg_id = [to_snowflake(k) for k in key.split("|")]
                author = await self.cache.get_member(guild_id, poll.author_id)
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

    @dis_snek.slash_command(name="quiz_me", description="Are you smarter than a 5th grader?", scopes=[891613945356492890])
    async def quiz_me(self, ctx: dis_snek.InteractionContext):
        modal = dis_snek.Modal(
            title="Are you smarter than a 5th grader?",
            components=[
                dis_snek.InputText(
                    label="What’s 25 x 3?",
                    custom_id="25x3",
                    placeholder="Answer",
                    style=dis_snek.TextStyles.SHORT,
                )
            ],
        )
        await ctx.send_modal(modal)

        # now we can wait for the modal
        try:
            modal_response = await bot.wait_for_modal(modal, timeout=500)

            if modal_response.responses.get("25x3") == "75":  # reponses is a dict of all the modal feilds
                await modal_response.send("Correct!")
            else:
                await modal_response.send("Incorrect!")

        except asyncio.TimeoutError:  # since we have a timeout, we can assume the user closed the modal
            return

    # ----------------------------------------------------------------------------------------------------------------------



    @slash_command(
        "reload",
        "Reloads all scales on the snek"
    )
    async def reload(self, ctx: InteractionContext):
        if ctx.author.has_permission(Permissions.MANAGE_ROLES):
            scale_names = []
            for scale in list(bot.scales.values()):
                name = str(scale).split('.')
                scale_names.append(name)
                # if scale != "Admin":
                bot.regrow_scale(f"scales.{name[1]}")
            scales_list = str(bot.scales.keys()).strip('dict_keys([').replace("'", "").replace("]", "").replace(')', '')
            await ctx.send(f"Reloaded Scales:\n```{scales_list}```")
        else:
            await ctx.send("You are lacking permissions to manage roles and therefore cannot reload the bot")

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
        await ctx.defer(ephemeral=True)

        poll = PollData.from_ctx(ctx)

        msg = await poll.send(await self.cache.get_channel(poll.channel_id))
        await self.set_poll(ctx.guild_id, msg.id, poll)
        await ctx.send("To close the poll, react to it with 🔴")

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
            u_perms = await ctx.author.channel_permissions(channel)
            if Permissions.SEND_MESSAGES not in u_perms:
                return await ctx.send(
                    f"You do not have permission to send messages in {channel.mention}"
                )

        poll = PollData.from_ctx(ctx)
        poll.poll_options.append(PollOption("Yes", booleanEmoji[0]))
        poll.poll_options.append(PollOption("No", booleanEmoji[1]))

        msg = await poll.send(await self.cache.get_channel(poll.channel_id))
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

    @slash_command("about", "Want to learn more about the bot?")
    async def about(self, ctx: InteractionContext):
        embed = Embed(title="About me",
                      color=color.FlatUIColors.AMETHYST,
                      description="Hi there!\n\n" \
                      "I'm Janet, an all-round utility / moderation bot.\n" \
                      "I am based off [Inquiry](https://github.com/LordOfPolls/Inquiry) which is an amazing bot made using [Dis-Snek](https://github.com/Discord-Snake-Pit/Dis-Snek)\n\n" \

                      "I'm the next generation of [Prism Bot](https://github.com/BoredManCodes/Prism-Bot) which started as a bot for only one guild, this version aims to be a public version\n\n" \

                      "Welcome to The Good Place")
        embed.set_image(url="https://cdn.discordapp.com/attachments/943106707381444678/943106731377037332/unknown.png")
        await ctx.send(embeds=embed)

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
                            msg = await self.cache.get_message(
                                poll.channel_id, poll.message_id
                            )
                            if msg:
                                await msg.edit(
                                    embeds=poll.embed, components=poll.components
                                )
                        self.polls_to_update[guild].remove(poll_id)
                    await asyncio.sleep(0)

    @dis_snek.message_command()
    async def begin(self, ctx: MessageContext, arg: CMD_BODY):
        if not self.available.is_set():
            await ctx.send("Waiting for current tests to complete...")
            await self.available.wait()

        if ctx.guild.id == 891613945356492890:
            if ctx.author.id != self.owner.id:
                return await ctx.send(
                    f"Only {self.owner.mention} can use the test suite"
                )

        self.available.clear()

        source = await ctx.send(
            "<a:loading:950666903540625418> Running dis_snek test suite..."
        )
        s = time.perf_counter()

        methods = inspect.getmembers(self.scales["Tests"], inspect.ismethod)

        for name, method in methods:
            if name.startswith("test_"):
                if arg:
                    if arg.lower() not in name:
                        continue
                test_title = f"{method.__name__.removeprefix('test_')} Tests".title()

                msg = await ctx.send(
                    f"<a:loading:950666903540625418> {test_title}: Running!"
                )
                try:
                    await method(ctx, msg)
                except Exception as e:
                    trace = "\n".join(traceback.format_exception(e))
                    await msg.edit(f"❌ {test_title}: Failed \n```{trace}```")
                else:
                    await msg.edit(f"✅ {test_title}: Completed")

        dur = time.perf_counter() - s

        await source.edit("✅ Dis_snek Test Suite: Completed")

        await ctx.send(f"Tests completed in {round(dur, 2)} seconds")

        self.available.set()

    @slash_command("twitch_avatar", "Get a user's Twitch avatar")
    @slash_option("username", "The username to lookup", opt_type=OptionTypes.STRING, required=True)
    async def twitch_avatar(self, ctx: InteractionContext, username: str):
        '''Gives you the avatar that a specified Twitch.tv user has'''

        # Set up your headers - in an actual application you'd
        # want these to be in init or a config file
        headers = {
            'Authorization': '5c8ftpbbhbw6wmp03glcufpkrmqsng'  # This is a fake token
        }

        # URL is a constant each time, params will change every time the command is called
        url = 'https://api.twitch.tv/helix/users'
        params = {
            'login': username
        }

        # Send the request - aiohttp is a non-blocking form of requests
        # In an actual application, you may have a single ClientSession that you use through the
        # whole cog, or perhaps the whole bot
        # In this example I'm just making one every time the command is called
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as r:
                response = await r.json()  # Get a json response
                print(response)
        # Respond with their avatar
        avatar = response['data'][0]['profile_image_url']
        await ctx.send(avatar)

bot = Bot()

bot.grow_scale("scales.database_management")
bot.grow_scale("scales.admin")
bot.grow_scale("scales.message_events")
bot.grow_scale("scales.debug")
bot.grow_scale("scales.other_events")
bot.grow_scale("scales.message_commands")
bot.grow_scale("scales.contexts")
bot.grow_scale("scales.application_commands")
bot.grow_scale("scales.arrest_management")
bot.grow_scale("scales.permission_management")
bot.grow_scale("scales.utilities")
bot.grow_scale("scales.tests")
# bot.grow_scale("scales.twitch")
bot.start(ConfigSectionMap("DiscordSettings")["token"])
print(bot)
