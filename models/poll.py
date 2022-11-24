import asyncio
import datetime
import logging
import re
import textwrap
from contextlib import suppress
from typing import Union, TYPE_CHECKING

import attr
import naff
import orjson
from naff import (
    ModalContext,
    MISSING,
    ButtonStyles,
    Color,
    ActionRow,
    Permissions,
    ThreadChannel,
    EMBED_MAX_NAME_LENGTH,
    to_optional_snowflake,
    Member,
    EmbedField,
    to_snowflake,
)
from naff.client.errors import NotFound, Forbidden, HTTPException
from naff.client.utils import no_export_meta
from naff.client.utils.serializer import _to_dict_any
from naff.models import (
    Snowflake_Type,
    Embed,
    BrandColors,
    MaterialColors,
    TimestampStyles,
    Timestamp,
    Button,
    spread_to_rows,
    Message,
    InteractionContext,
)
from naff.models.discord.base import ClientObject

from const import process_duration
from models.emoji import default_emoji
from models.events import PollCreate, PollClose, PollVote
from models.poll_option import PollOption

if TYPE_CHECKING:
    pass

__all__ = ("deserialize_datetime", "PollData", "sanity_check")

log = logging.getLogger("Inquiry")

channel_mention = re.compile(r"<#(\d{17,})>")
role_mention = re.compile(r"<@&(\d{17,})")
user_mention = re.compile(r"<@!?(\d{17,})>")


def deserialize_datetime(date) -> datetime.datetime:
    if isinstance(date, str):
        return datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f")
    return date


async def sanity_check(ctx: InteractionContext) -> bool:
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

    if ctx.kwargs.get("thread"):
        if isinstance(ctx.channel, ThreadChannel):
            await ctx.send("You can't make a thread inside a thread", ephemeral=True)
            return False
        if not all(perm in channel_perms for perm in (Permissions.USE_PUBLIC_THREADS, Permissions.USE_PRIVATE_THREADS)):
            await ctx.send("I don't have the permissions to create threads in this channel", ephemeral=True)
            return False
        if isinstance(ctx.channel, ThreadChannel):
            await ctx.send("You cannot create a thread inside a thread!", ephemeral=True)
            return False
        if len(ctx.kwargs.get("title")) > 100:
            await ctx.send("Thread titles cannot be longer than 100 characters", ephemeral=True)
            return False

    if ctx.kwargs.get("close_message"):
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

    if ctx.kwargs.get("vote_to_view", None) is True and ctx.kwargs.get("hide_results") is False:
        await ctx.send("You cannot enable `vote_to_view` and disable `hide_results`", ephemeral=True)
        return False

    if ctx.kwargs.get("hide_author", False) is True:
        user_perms = ctx.channel.permissions_for(ctx.author)
        if Permissions.MANAGE_MESSAGES not in user_perms:
            await ctx.send("You must have the `manage_messages` permission to hide the author", ephemeral=True)
            return False

    return True


@attr.s(auto_attribs=True, on_setattr=[attr.setters.convert, attr.setters.validate], kw_only=True)
class PollData(ClientObject):
    title: str
    author_id: Snowflake_Type
    description: str = attr.ib(default=None)
    channel_id: Snowflake_Type = attr.ib(default=MISSING)
    message_id: Snowflake_Type = attr.ib(default=MISSING)
    thread_message_id: Snowflake_Type = attr.ib(default=MISSING)
    guild_id: Snowflake_Type = attr.ib(default=MISSING)

    author_name: str = attr.ib(default=MISSING)
    author_avatar: str = attr.ib(default=MISSING)
    author_hidden: bool = attr.ib(default=False)

    poll_options: list[PollOption] = attr.ib(
        factory=list,
        converter=lambda options: [PollOption.deserialize(o) if not isinstance(o, PollOption) else o for o in options],
        metadata={"export_converter": str},
    )

    max_votes: int | None = attr.ib(default=None)
    voting_role: Snowflake_Type | None = attr.ib(default=None)
    hide_results: bool = attr.ib(default=False)
    vote_to_view: bool = attr.ib(default=False)
    anonymous: bool = attr.ib(default=False)
    open_poll: bool = attr.ib(default=False)
    show_option_author: bool = attr.ib(default=False)
    inline: bool = attr.ib(default=False)
    thread: bool = attr.ib(default=False)
    close_message: bool = attr.ib(default=False)
    proportional_results: bool = attr.ib(default=False)

    colour: str = attr.ib(default="BLURPLE", converter=lambda x: x.upper())
    image_url: str = attr.ib(default=MISSING)

    _sent_close_message: bool = attr.ib(default=False)

    expire_time: datetime = attr.ib(default=MISSING, converter=deserialize_datetime)

    poll_type: str = attr.ib(default="default")
    _expired: bool = attr.ib(default=False)
    deleted: bool = attr.ib(default=False, metadata=no_export_meta)
    closed: bool = attr.ib(default=False)
    lock: asyncio.Lock = attr.ib(factory=asyncio.Lock, metadata=no_export_meta)
    # todo: future polls: as cool as this is, its ugly. refactor pls :(
    latest_context: InteractionContext | None = attr.ib(default=MISSING, init=False, metadata=no_export_meta)

    def as_dict(self) -> dict:
        data = {
            k.removeprefix("_"): v
            for k, v in attr.asdict(self).items()
            if v != MISSING and not isinstance(v, (asyncio.Lock, naff.Client))
        }
        data["poll_options"] = orjson.dumps(data.pop("poll_options")).decode()
        del data["deleted"]
        return data

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

    def get_colour(self, *, ignore_expired: bool = False) -> Color:
        if self.expired and not ignore_expired:
            return MaterialColors.GREY
        if self.colour in MaterialColors.__members__:
            return MaterialColors[self.colour]
        elif self.colour in BrandColors.__members__:
            return BrandColors[self.colour]
        else:
            return BrandColors.BLURPLE

    @property
    def voters(self) -> set[Snowflake_Type]:
        return {v for o in self.poll_options for v in o.voters}

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

    @property
    def close_embed(self) -> Embed:
        embed = Embed(
            title="Poll Closed",
            description="This poll has been closed",
            color=self.get_colour(),
        )
        embed.add_field(name="Poll Name", value=self.title, inline=False)

        if self.total_votes != 0:
            sorted_votes: list[PollOption] = sorted(self.poll_options, key=lambda x: len(x.voters), reverse=True)
            possible_ties = [o for o in sorted_votes if len(o.voters) == len(sorted_votes[0].voters)]
            if len(possible_ties) == 1:
                embed.add_field(
                    name="Highest Voted Option",
                    value=f"{possible_ties[0].emoji} {possible_ties[0].text} - {possible_ties[0].create_bar(len(self.voters) if self.proportional_results else self.total_votes)}",
                )
            else:
                embed.add_field(
                    name="Tied Highest Voted Options",
                    value="\n".join(
                        [
                            f"{o.emoji} {o.text}\n{o.create_bar(len(self.voters) if self.proportional_results else self.total_votes)}"
                            for o in possible_ties
                        ]
                    ),
                )
        else:
            embed.add_field(name="Highest Voted Option", value="No votes were cast")

        embed.set_footer(text=f"Poll ID: {self.message_id}")
        return embed

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

    @property
    def results_embed(self) -> Embed:
        embed = Embed("Poll Results", color=self.get_colour())
        embed.fields = self.get_option_fields(force_display=True)
        return embed

    @property
    def embed(self) -> Embed:
        e = Embed(
            f"{self.title}" if self.title else "Poll:",
            "",
            color=self.get_colour() if not self.expired else MaterialColors.GREY,
        )
        total_votes = self.total_votes

        e.fields = self.get_option_fields()

        if self.image_url:
            e.set_image(url=self.image_url)

        description = []
        if self.description:
            description.append(self.description)

        if self.single_vote:
            description.append(f"• {total_votes:,} vote{'s' if total_votes != 1 else ''}")
        else:
            description.append(
                f"• {total_votes:,} vote{'s' if total_votes != 1 else ''} cast by {len(self.voters):,} user{'s' if len(self.voters) != 1 else ''}"
            )

        if self.poll_type != "default":
            description.append(f"• {self.poll_type.title()} Poll")

        if self.single_vote:
            description.append("• One Vote Per User")
        elif self.max_votes:
            description.append(f"• {self.max_votes} Votes Per User")

        if self.proportional_results:
            description.append("• Proportional Results")

        if self.vote_to_view:
            description.append("• Vote To View Results")
        elif self.hide_results:
            if self.expired:
                description.append("• Results were hidden until the poll ended")
            else:
                description.append("• Results are hidden until the poll ends")

        if self.anonymous:
            description.append("• Anonymous Voting")

        if self.voting_role:
            description.append(f"• Required Role: <@&{self.voting_role}>")

        if self.open_poll:
            description.append("• Open Poll - Anyone can add options")

        if len(self.poll_options) == 0:
            e.add_field("This poll has no options", "Be the first to add one with the `+` button!", inline=False)

        if self.expire_time:
            _c = "Closed" if self.expired else "Closes"
            description.append(
                f"• {_c} {Timestamp.fromdatetime(self.expire_time).format(TimestampStyles.RelativeTime)}"
            )

        e.description = "\n".join(description)

        if self.author_hidden:
            e.set_footer(text=f"Asked by Server Staff", icon_url=self.author_avatar)
        else:
            e.set_footer(f"Asked by {self.author_name}", icon_url=self.author_avatar)

        if self.expired:
            name = f" • Asked by {self.author_name}" if self.author_name else ""
            e.set_footer(f"This poll has ended{name}")

        return e

    def reallocate_emoji(self):
        """Reallocate emoji to the poll options"""
        for i, option in enumerate(self.poll_options):
            if option.emoji in default_emoji:
                option.emoji = default_emoji[i]

    def get_components(self, *, disable: bool = False) -> list[ActionRow]:
        if self.expired and not disable:
            return []
        buttons = []
        extra_buttons = []

        for i in range(len(self.poll_options)):
            buttons.append(
                Button(1, emoji=self.poll_options[i].emoji, custom_id=f"poll_option|{i}", disabled=self.expired),
            )
        if self.vote_to_view and len(self.poll_options) < 25:
            buttons.append(
                Button(ButtonStyles.GREEN, emoji="\U0001f441", custom_id="vote_to_view"),
            )
        if self.open_poll and len(self.poll_options) < 25:
            buttons.append(
                Button(ButtonStyles.SUCCESS, emoji="\U00002795", custom_id="add_option", disabled=self.expired)
            )

        return spread_to_rows(*buttons)

    def add_option(self, author: Snowflake_Type, opt_name: str, _emoji: str | None = None) -> None:
        if len(self.poll_options) >= len(default_emoji):
            raise ValueError("Poll has reached max options")

        self.poll_options.append(PollOption.parse(self, author, opt_name, _emoji))

    def parse_message(self, msg: Message) -> None:
        self.channel_id = msg.channel.id
        self.message_id = msg.id

    @classmethod
    async def from_ctx(cls, ctx: InteractionContext, m_ctx: ModalContext | None = None) -> Union["PollData", bool]:
        if not await sanity_check(ctx):
            return False

        kwargs = ctx.kwargs
        if m_ctx:
            kwargs |= m_ctx.kwargs
        new_cls: "PollData" = cls(
            client=ctx.bot,
            title=kwargs.get("title"),
            description=kwargs.get("description", None),
            author_id=ctx.author.id,
            max_votes=kwargs.get("max_votes", None),
            hide_results=kwargs.get("hide_results", False),
            vote_to_view=kwargs.get("vote_to_view", False),
            open_poll=kwargs.get("open_poll", False),
            show_option_author=kwargs.get("show_option_author", False),
            inline=kwargs.get("inline", False),
            colour=kwargs.get("colour", "BLURPLE"),
            thread=kwargs.get("thread", False),
            channel_id=ctx.channel.id,
            guild_id=ctx.guild.id,
            author_name=ctx.author.display_name,
            author_avatar=ctx.author.avatar.url,
            close_message=kwargs.get("close_message", False),
            voting_role=to_optional_snowflake(kwargs.get("voting_role", None)),
            anonymous=kwargs.get("anonymous", False),
            proportional_results=kwargs.get("proportional_results", False),
            author_hidden=kwargs.get("hide_author", False),
        )
        if new_cls.author_hidden:
            if ctx.guild.icon:
                new_cls.author_avatar = ctx.guild.icon.url
            else:
                new_cls.author_avatar = ctx.bot.user.avatar.url

        # handle discord not allowing mentions in titles
        for channel_id in channel_mention.findall(new_cls.title):
            if channel_id and (channel := ctx.bot.get_channel(channel_id)):
                new_cls.title = new_cls.title.replace(channel.mention, f"#{channel.name}")

        for role_id in role_mention.findall(new_cls.title):
            if role_id and (role := ctx.guild.get_role(role_id)):
                new_cls.title = new_cls.title.replace(role.mention, f"@{role.name}")

        for user_id in user_mention.findall(new_cls.title):
            if user_id and (user := ctx.guild.get_member(user_id)):
                new_cls.title = new_cls.title.replace(user.mention, f"@{user.tag}")

        if options := kwargs.get("options"):
            if not isinstance(options, list):
                options = options.split("\n")

            for o in options:
                if o:
                    new_cls.add_option(ctx.author, o.strip().removeprefix("-"))

        if view_state := kwargs.get("view_results"):
            match view_state:
                # these don't need to be so explicit but clarity is nice
                case "always":
                    new_cls.hide_results = False
                    new_cls.vote_to_view = False
                case "after_voting":
                    new_cls.hide_results = True
                    new_cls.vote_to_view = True
                case "after_voting_closed":
                    new_cls.hide_results = True
                    new_cls.vote_to_view = False
                case _:
                    new_cls.hide_results = False
                    new_cls.vote_to_view = False

        if new_cls.vote_to_view and not new_cls.hide_results:
            new_cls.hide_results = True

        if attachment := kwargs.get("image"):
            new_cls.image_url = attachment.url

        if duration := kwargs.get("duration"):
            new_cls.expire_time = process_duration(duration)

        return new_cls

    async def send(self, context: InteractionContext) -> Message:
        self.latest_context = context
        try:
            msg = await context.send(embeds=self.embed, components=[] if self.expired else self.get_components())
            self.parse_message(msg)
            if self.thread:
                thread = await msg.create_thread(self.title, reason=f"Poll created for {context.author.username}")
                # thread_msg = await thread.send(components=self.get_components(disable=True))
                # self.thread_message_id = thread_msg.id

            if self.expire_time:
                await context.bot.schedule_close(self)

            self._client.dispatch(PollCreate(self, context))

            return msg
        except Exception:
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

    def get_user_votes(self, user_id: int) -> list[PollOption]:
        return [option for option in self.poll_options if option.has_voted(user_id)]

    def _vote(self, option: PollOption, user: Member) -> bool:
        return option.vote(user.id)

    async def _vote_check(self, ctx: InteractionContext, option: PollOption) -> bool:
        """A placeholder for future checks in subclasses"""
        return True

    @property
    def vote_added_text(self) -> str:
        return "Your vote has been added."

    @property
    def vote_removed_text(self) -> str:
        return "Your vote has been removed."

    async def vote(self, ctx: InteractionContext):
        self.latest_context = ctx
        try:
            if self.expired:
                message = await self._client.cache.fetch_message(self.channel_id, self.message_id)
                await message.edit(components=self.get_components(disable=True))
                await ctx.send("This poll is closing - your vote will not be counted", ephemeral=True)
                return
            else:
                async with self.lock:
                    if (
                        self.voting_role
                        and self.voting_role != ctx.guild_id
                        and not ctx.author.has_role(self.voting_role)
                    ):
                        return await ctx.send("You do not have permission to vote in this poll", ephemeral=True)
                    option_index = int(ctx.custom_id.removeprefix("poll_option|"))
                    option = self.poll_options[option_index]

                    if self.single_vote:
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
                                embed.add_field(
                                    "Your Votes", ", ".join([f"`{o.emoji} {o.text}`" for o in voted_options])
                                )
                                embed.add_field("To remove a vote", "Vote again for the option you want to remove")
                                return await ctx.send(embed=embed, ephemeral=True)

                    if not await self._vote_check(ctx, option):
                        return

                    if self._vote(option, ctx.author):
                        log.info(f"Added vote to {self.message_id}")
                        embed = Embed(self.vote_added_text, color=BrandColors.GREEN)
                        embed.add_field("Option", f"⬆️ {option.emoji} `{option.text}`")
                        await ctx.send(embed=embed, ephemeral=True)
                    else:
                        log.info(f"Removed vote from {self.message_id}")
                        embed = Embed(self.vote_removed_text, color=BrandColors.GREEN)
                        embed.add_field("Option", f"⬇️ {option.emoji} `{option.text}`")
                        await ctx.send(embed=embed, ephemeral=True)
                    self._client.dispatch(PollVote(self, ctx.guild.id))
        except Forbidden:
            pass

    def has_voted(self, user: Snowflake_Type) -> bool:
        user = to_snowflake(user)
        return any([option.has_voted(user) for option in self.poll_options])
