import asyncio
import datetime
import logging
import re
import textwrap
from abc import abstractmethod
from contextlib import suppress
from typing import TypeVar

import attr
import naff
import orjson
from naff import (
    InteractionContext,
    Snowflake_Type,
    MISSING,
    MaterialColors,
    BrandColors,
    Color,
    Embed,
    EMBED_MAX_NAME_LENGTH,
    EmbedField,
    ActionRow,
    Button,
    ButtonStyles,
    spread_to_rows,
    ModalContext,
    to_optional_snowflake,
    ThreadChannel,
    Permissions,
    Timestamp,
    Message,
    to_snowflake,
    Member,
)
from naff.client.errors import Forbidden, NotFound, HTTPException
from naff.client.utils import no_export_meta
from naff.models.discord.base import ClientObject

from const import process_duration
from models.emoji import default_emoji, opinion_emoji
from models.events import PollClose, PollCreate, PollVote
from models.poll_option import PollOption

T = TypeVar("T")

log = logging.getLogger("Inquiry")
channel_mention = re.compile(r"<#(\d{17,})>")
role_mention = re.compile(r"<@&(\d{17,})")
user_mention = re.compile(r"<@!?(\d{17,})>")


def deserialize_datetime(date) -> datetime.datetime:
    if isinstance(date, str):
        return datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f")
    return date


@attr.s(auto_attribs=True, on_setattr=[attr.setters.convert, attr.setters.validate], kw_only=True)
class BasePoll(ClientObject):
    """The basic poll model

    Should be subclassed to create a new type of poll.
    """

    poll_type: str = attr.ib(default="base", init=False)

    # operational attributes
    title: str
    description: str = attr.ib(default=None)
    colour: str = attr.ib(default="BLURPLE", converter=lambda x: x.upper())
    image_url: str = attr.ib(default=MISSING)

    author_id: Snowflake_Type
    channel_id: Snowflake_Type = attr.ib(default=MISSING)
    message_id: Snowflake_Type = attr.ib(default=MISSING)
    guild_id: Snowflake_Type = attr.ib(default=MISSING)

    author_name: str = attr.ib(default=MISSING)
    author_avatar: str = attr.ib(default=MISSING)

    poll_options: list[PollOption] = attr.ib(
        factory=list,
        converter=lambda options: [PollOption.deserialize(o) if not isinstance(o, PollOption) else o for o in options],
        metadata={"export_converter": str},
    )

    # config
    anonymous: bool = attr.ib(default=False)
    author_hidden: bool = attr.ib(default=False)
    close_message: bool = attr.ib(default=False)
    hide_results: bool = attr.ib(default=False)
    inline: bool = attr.ib(default=False)
    max_votes: int | None = attr.ib(default=None)
    open_poll: bool = attr.ib(default=False)
    proportional_results: bool = attr.ib(default=False)
    show_option_author: bool = attr.ib(default=False)
    thread: bool = attr.ib(default=False)
    vote_to_view: bool = attr.ib(default=False)
    voting_role: Snowflake_Type | None = attr.ib(default=None)

    # time
    expire_time: datetime.datetime = attr.ib(default=MISSING, converter=deserialize_datetime)
    open_time: datetime.datetime = attr.ib(default=MISSING, converter=deserialize_datetime)

    # state
    closed: bool = attr.ib(default=False)
    deleted: bool = attr.ib(default=False, metadata=no_export_meta)

    _expired: bool = attr.ib(default=False)
    _pending: bool = attr.ib(default=False)
    _sent_close_message: bool = attr.ib(default=False)

    lock: asyncio.Lock = attr.ib(factory=asyncio.Lock, metadata=no_export_meta)
    latest_context: InteractionContext | None = attr.ib(default=MISSING, init=False, metadata=no_export_meta)

    @property
    def pending(self) -> bool:
        if self._pending:
            return True
        if self.open_time:
            if self.open_time > datetime.datetime.now():
                return True
        return False

    @property
    def expired(self) -> bool:
        if self._expired:
            return True
        if self.expire_time:
            if self.expire_time < datetime.datetime.now():
                self._expired = True
                return True
        return False

    @property
    def single_vote(self) -> bool:
        return self.max_votes == 1

    @property
    def total_votes(self) -> int:
        votes = 0
        for o in self.poll_options:
            votes += len(o.voters)
        return votes

    @property
    def voters(self) -> set[Snowflake_Type]:
        return {v for o in self.poll_options for v in o.voters}

    @property
    def maximum_options(self) -> int:
        return len(default_emoji)

    @property
    @abstractmethod
    def embed(self) -> Embed:
        raise NotImplementedError

    @property
    @abstractmethod
    def close_embed(self) -> naff.Embed:
        """The embed to send when the poll is closed"""
        raise NotImplementedError

    @property
    def results_embed(self) -> Embed:
        embed = Embed("Poll Results", color=self.get_colour())
        embed.fields = self.get_option_fields(force_display=True)
        return embed

    @property
    def vote_added_text(self) -> str:
        return "Your vote has been added."

    @property
    def vote_removed_text(self) -> str:
        return "Your vote has been removed."

    async def sanity_check(self, ctx: InteractionContext, kwargs: dict) -> bool:
        """Sanity checks that the bot can even make a poll here"""
        if not ctx.guild:
            # technically shouldn't happen, but no harm in checking
            await ctx.send("This command can only be used in a server", ephemeral=True)
            return False
        if not isinstance(ctx.channel, ThreadChannel):
            channel = ctx.channel
        else:
            channel = ctx.channel.parent_channel
        channel_perms = channel.permissions_for(ctx.guild.me)

        if kwargs.get("thread"):
            if isinstance(ctx.channel, ThreadChannel):
                await ctx.send("You can't make a thread inside a thread", ephemeral=True)
                return False
            if not all(
                perm in channel_perms for perm in (Permissions.USE_PUBLIC_THREADS, Permissions.USE_PRIVATE_THREADS)
            ):
                await ctx.send("I don't have the permissions to create threads in this channel", ephemeral=True)
                return False
            if isinstance(ctx.channel, ThreadChannel):
                await ctx.send("You cannot create a thread inside a thread!", ephemeral=True)
                return False
            if len(ctx.kwargs.get("title")) > 100:
                await ctx.send("Thread titles cannot be longer than 100 characters", ephemeral=True)
                return False

        if kwargs.get("close_message"):
            if Permissions.SEND_MESSAGES not in channel_perms:
                await ctx.send(
                    "Unable to use `close_message` in this channel - Please enable the `send_messages` permission in this channel",
                    ephemeral=True,
                )
                return False
            if Permissions.READ_MESSAGE_HISTORY not in channel_perms:
                await ctx.send(
                    "Unable to use `close_message` in this channel - Please enable the `read_message_history` permission in this channel",
                    ephemeral=True,
                )
                return False

        if kwargs.get("vote_to_view", None) is True and ctx.kwargs.get("hide_results") is False:
            await ctx.send("You cannot enable `vote_to_view` and disable `hide_results`", ephemeral=True)
            return False

        if kwargs.get("hide_author", False) is True:
            user_perms = ctx.channel.permissions_for(ctx.author)
            if Permissions.MANAGE_MESSAGES not in user_perms:
                await ctx.send("You must have the `manage_messages` permission to hide the author", ephemeral=True)
                return False
            if Permissions.SEND_MESSAGES not in channel_perms:
                await ctx.send("I cannot hide the author if I cannot send messages", ephemeral=True)
                return False

        return True

    @classmethod
    async def from_ctx(cls, ctx: InteractionContext, m_ctx: ModalContext | None = None) -> T:
        """Create a new poll from context"""
        kwargs = ctx.kwargs
        if m_ctx:
            kwargs |= m_ctx.kwargs

        instance: T = cls(
            client=ctx.bot,
            title=kwargs.get("title"),
            description=kwargs.get("description", None),
            anonymous=kwargs.get("anonymous", False),
            author_avatar=ctx.author.avatar.url,
            author_hidden=kwargs.get("hide_author", False),
            author_id=ctx.author.id,
            author_name=ctx.author.display_name,
            channel_id=ctx.channel.id,
            close_message=kwargs.get("close_message", False),
            colour=kwargs.get("colour", "BLURPLE"),
            guild_id=ctx.guild.id,
            hide_results=kwargs.get("hide_results", False),
            inline=kwargs.get("inline", False),
            max_votes=kwargs.get("max_votes", None),
            open_poll=kwargs.get("open_poll", False),
            proportional_results=kwargs.get("proportional_results", False),
            show_option_author=kwargs.get("show_option_author", False),
            thread=kwargs.get("thread", False),
            vote_to_view=kwargs.get("vote_to_view", False),
            voting_role=to_optional_snowflake(kwargs.get("voting_role", None)),
        )

        if not await instance.sanity_check(ctx, kwargs):
            raise RuntimeError("Sanity check failed")

        # sanitize mentions
        for channel_id in channel_mention.findall(instance.title):
            if channel_id and (channel := ctx.bot.get_channel(channel_id)):
                instance.title = instance.title.replace(channel.mention, f"#{channel.name}")

        for role_id in role_mention.findall(instance.title):
            if role_id and (role := ctx.guild.get_role(role_id)):
                instance.title = instance.title.replace(role.mention, f"@{role.name}")

        for user_id in user_mention.findall(instance.title):
            if user_id and (user := ctx.guild.get_member(user_id)):
                instance.title = instance.title.replace(user.mention, f"@{user.tag}")

        # process options
        if options := kwargs.get("options"):
            if not isinstance(options, list):
                options = options.split("\n")

            for o in options:
                if o:
                    instance.add_option(ctx.author, o.strip().removeprefix("-"))

        # configure poll visibility
        if view_state := kwargs.get("view_results"):
            match view_state:
                # these don't need to be so explicit but clarity is nice
                case "always":
                    instance.hide_results = False
                    instance.vote_to_view = False
                case "after_voting":
                    instance.hide_results = True
                    instance.vote_to_view = True
                case "after_voting_closed":
                    instance.hide_results = True
                    instance.vote_to_view = False
                case _:
                    instance.hide_results = False
                    instance.vote_to_view = False

        if instance.author_hidden:
            if ctx.guild.icon:
                instance.author_avatar = ctx.guild.icon.url
            else:
                instance.author_avatar = ctx.bot.user.avatar.url

        if attachment := kwargs.get("image"):
            instance.image_url = attachment.url

        # timing config
        if open_time := kwargs.get("open_in"):
            instance.open_time = process_duration(open_time)
            instance._pending = True

        if duration := kwargs.get("duration"):
            instance.expire_time = process_duration(duration, start_time=instance.open_time)
        return instance

    def reallocate_emoji(self):
        """Reallocate emoji to the poll options"""
        for i, option in enumerate(self.poll_options):
            if option.emoji in default_emoji:
                option.emoji = default_emoji[i]

    def get_option_fields(self, *, force_display: bool = False) -> list[EmbedField]:
        fields = []
        all_voters = self.voters
        hide_results = self.hide_results and not force_display

        for o in self.poll_options:
            name = textwrap.shorten(f"{o.emoji} {o.text}", width=EMBED_MAX_NAME_LENGTH)
            author = f" - <@{o.author_id}>" if self.show_option_author else ""

            if not self.expired and hide_results:
                fields.append(EmbedField(name=name, value=author if author else "‏", inline=self.inline))
            else:
                fields.append(
                    EmbedField(
                        name=name,
                        value=f"{o.create_bar(len(all_voters) if self.proportional_results else self.total_votes)}{author}",
                        inline=self.inline,
                    )
                )
        return fields

    def get_colour(self, *, ignore_expired: bool = False) -> Color:
        if self.expired and not ignore_expired:
            return MaterialColors.GREY
        if self.colour in MaterialColors.__members__:
            return MaterialColors[self.colour]
        elif self.colour in BrandColors.__members__:
            return BrandColors[self.colour]
        else:
            return BrandColors.BLURPLE

    def get_components(self, *, disable: bool = False) -> list[ActionRow]:
        if self.expired and not disable:
            return []
        disable_buttons = self.expired or self.pending

        buttons = []

        for i in range(len(self.poll_options)):
            buttons.append(
                Button(1, emoji=self.poll_options[i].emoji, custom_id=f"poll_option|{i}", disabled=disable_buttons),
            )
        if self.vote_to_view and len(self.poll_options) < 25:
            buttons.append(
                Button(ButtonStyles.GREEN, emoji="\U0001f441", custom_id="vote_to_view"),
            )
        if self.open_poll and len(self.poll_options) < 25:
            buttons.append(
                Button(ButtonStyles.SUCCESS, emoji="\U00002795", custom_id="add_option", disabled=disable_buttons)
            )

        return spread_to_rows(*buttons)

    def as_dict(self) -> dict:
        """Convert the poll to a dict"""
        data = {
            k.removeprefix("_"): v
            for k, v in attr.asdict(self).items()
            if v != MISSING and not isinstance(v, (asyncio.Lock, naff.Client))
        }
        data["poll_options"] = orjson.dumps(data.pop("poll_options")).decode()
        del data["deleted"]
        return data

    async def cache_all_voters(self):
        sem = asyncio.Semaphore(10)

        uncached_voters = [v for v in self.voters if v not in self._client.cache.user_cache]
        if uncached_voters:
            log.debug(f"Caching {len(uncached_voters)} voters for poll {self.message_id}")

            async def fetch_voter(v) -> None:
                async with sem:
                    with suppress(Forbidden, NotFound):
                        await self._client.cache.fetch_user(v)

            await asyncio.gather(*[fetch_voter(v) for v in uncached_voters])

    def has_voted(self, user: Snowflake_Type) -> bool:
        user = to_snowflake(user)
        return any([option.has_voted(user) for option in self.poll_options])

    async def send(self, context: InteractionContext) -> Message:
        self.latest_context = context
        try:
            if self.author_hidden:
                msg = await context.channel.send(
                    embeds=self.embed, components=[] if self.expired else self.get_components()
                )
                await context.send(f"[Poll created]({msg.jump_url})", ephemeral=True)
            else:
                msg = await context.send(embeds=self.embed, components=[] if self.expired else self.get_components())

            self.channel_id = msg.channel.id
            self.message_id = msg.id
            if self.thread:
                await msg.create_thread(self.title, reason=f"Poll created for {context.author.username}")

            if self.open_time:
                await context.bot.schedule_open(self)
            elif self.expire_time:
                await context.bot.schedule_close(self)

            self._client.dispatch(PollCreate(self, context))

            return msg
        except Exception:
            await self._client.close_poll(self, failed=True)  # poll failed to send, close it
            raise

    async def send_close_message(self) -> None:
        self._client.dispatch(PollClose(self))
        if self.close_message and not self._sent_close_message:
            origin_message = await self._client.cache.fetch_message(self.channel_id, self.message_id)
            if origin_message:
                await origin_message.reply(embed=self.close_embed)
                self._sent_close_message = True

            # ping all users who voted
            all_voters = self.voters
            if all_voters:
                fields = self.get_option_fields(force_display=True)
                sem = asyncio.Semaphore(10)

                async def send_message(user_id: int) -> None:
                    async with sem:
                        user = await self._client.cache.fetch_user(user_id)
                        if user:
                            votes = [f"{o.emoji} {o.text}" for o in self.poll_options if user_id in o.voters]
                            embed = Embed(
                                title=f'"{self.title}" has ended',
                                description=f"**You voted for:** {', '.join(votes)}",
                                color=self.get_colour(ignore_expired=True),
                            )
                            embed.fields = fields
                            embed.set_footer(text="You are receiving this message because you voted in this poll.")
                            try:
                                await user.send(embed=embed)
                            except Forbidden:
                                pass

                log.info(f"Sending close message to {len(all_voters)} voters")
                await asyncio.gather(*[send_message(voter) for voter in all_voters])

    async def update_messages(self):
        self.reallocate_emoji()
        interaction_context = None

        if self.latest_context:
            age = (Timestamp.now() - Timestamp.from_snowflake(self.latest_context.interaction_id)).total_seconds()
            if age < 890:  # 15 minutes minus 10 seconds
                interaction_context = self.latest_context

        try:
            message = await self._client.cache.fetch_message(self.channel_id, self.message_id)

            try:
                await message.edit(embeds=self.embed, components=self.get_components(), context=interaction_context)
            except (NotFound, Forbidden, HTTPException):
                if interaction_context:
                    await message.edit(embeds=self.embed, components=self.get_components())
        except NotFound:
            log.warning(f"Poll {self.message_id} was not found in channel {self.channel_id} -- likely deleted by user")
        except Forbidden:
            log.warning(
                f"Poll {self.message_id} in channel {self.channel_id} cannot be edited -- likely permissions issue"
            )

    def add_option(self, author: Snowflake_Type, opt_name: str, _emoji: str | None = None) -> None:
        if len(self.poll_options) >= self.maximum_options:
            raise ValueError("Poll has reached max options")

        self.poll_options.append(PollOption.parse(self, author, opt_name, _emoji))

    def get_user_votes(self, user_id: int) -> list[PollOption]:
        return [option for option in self.poll_options if option.has_voted(user_id)]

    def _vote(self, option: PollOption, user: Member) -> bool:
        return option.vote(user.id)

    async def _vote_check(self, ctx: InteractionContext, option: PollOption) -> bool:
        """A placeholder for future checks in subclasses"""
        return True

    async def vote(self, ctx: InteractionContext):
        self.latest_context = ctx
        try:
            if self.expired:
                message = await self._client.cache.fetch_message(self.channel_id, self.message_id)
                await message.edit(components=self.get_components(disable=True))
                await ctx.send("This poll is closing - your vote will not be counted", ephemeral=True)
                return
            else:
                if self.voting_role and self.voting_role != ctx.guild_id and not ctx.author.has_role(self.voting_role):
                    return await ctx.send("You do not have permission to vote in this poll", ephemeral=True)
                option_index = int(ctx.custom_id.removeprefix("poll_option|"))
                option = self.poll_options[option_index]

                if self.single_vote:
                    async with self.lock:
                        for _o in self.poll_options:
                            if _o != option:
                                if ctx.author.id in _o.voters:
                                    _o.voters.remove(ctx.author.id)
                                    if _o.eliminated:
                                        _o.eliminated = False
                elif self.max_votes is not None:
                    voted_options = self.get_user_votes(ctx.author.id)

                    if len(voted_options) >= self.max_votes:
                        if not option.has_voted(ctx.author.id):
                            log.warning(
                                f"{self.message_id}|{ctx.author.id} tried to vote for more than the max votes allowed"
                            )
                            embed = Embed(
                                "You have already voted for the maximum number of options",
                                color=BrandColors.RED,
                            )
                            embed.add_field("Maximum Votes", self.max_votes)
                            embed.add_field("Your Votes", ", ".join([f"`{o.emoji} {o.text}`" for o in voted_options]))
                            embed.add_field("To remove a vote", "Vote again for the option you want to remove")
                            return await ctx.send(embed=embed, ephemeral=True)

                if not await self._vote_check(ctx, option):
                    return

                if option.has_voted(ctx.author.id):
                    await self.remove_vote_confirmation(ctx, option)
                else:
                    async with self.lock:
                        self._vote(option, ctx.author)
                    log.info(f"Added vote to {self.message_id}")
                    embed = Embed(self.vote_added_text, color=BrandColors.GREEN)
                    embed.add_field("Option", f"⬆️ {option.emoji} `{option.text}`")
                    await ctx.send(embed=embed, ephemeral=True)
                self._client.dispatch(PollVote(self, ctx.guild.id))
        except Forbidden:
            pass

    async def remove_vote_confirmation(self, ctx: InteractionContext, option: PollOption):
        embed = Embed(
            color=BrandColors.RED,
            description=f"You have already voted for {option.emoji} {option.text}\nWould you like to remove your vote?",
        )
        message = await ctx.send(
            embed=embed,
            components=[
                Button(ButtonStyles.GREEN, label="Yes", custom_id="poll_remove_vote|yes"),
                Button(ButtonStyles.RED, label="No", custom_id="poll_remove_vote|no"),
            ],
            ephemeral=True,
        )
        try:
            out = await self._client.wait_for_component(
                [message], timeout=30, check=lambda i: i.ctx.author.id == ctx.author.id
            )
        except asyncio.TimeoutError:
            await ctx.edit(message, embed=Embed("Timed out", color=BrandColors.RED), components=[])
        else:
            if out.ctx.custom_id == "poll_remove_vote|yes":
                async with self.lock:
                    self._vote(option, ctx.author)
                    log.info(f"Removed vote from {self.message_id}")
                embed = Embed(self.vote_removed_text, color=BrandColors.GREEN)
                embed.add_field("Option", f"⬇️ {option.emoji} `{option.text}`")

                await ctx.edit(
                    message,
                    embed=embed,
                    components=[],
                )
            else:
                await ctx.edit(message, embed=Embed("Vote not removed", color=BrandColors.RED), components=[])

    def add_preset_options(self, preset: str, author: Member):
        log.debug(f"Creating poll from preset: {preset}")

        match preset.lower():
            case "boolean":
                self.add_option(author, "Yes", "✅")
                self.add_option(author, "No", "❌")
            case "week":
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
                    self.add_option(author, opt)
            case "month":
                options = [
                    "January",
                    "February",
                    "March",
                    "April",
                    "May",
                    "June",
                    "July",
                    "August",
                    "September",
                    "October",
                    "November",
                    "December",
                ]
                for opt in options:
                    self.add_option(author, opt)
            case "opinion":
                self.add_option(author, "Agree", opinion_emoji[0])
                self.add_option(author, "Neutral", opinion_emoji[1])
                self.add_option(author, "Disagree", opinion_emoji[2])
            case "rating":
                for i in range(0, 10):
                    self.add_option(author, str(i + 1))
            case "rating_5":
                for i in range(0, 5):
                    self.add_option(author, str(i + 1))
            case _:
                raise ValueError("Invalid preset")
