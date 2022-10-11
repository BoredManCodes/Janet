import asyncio
import datetime
import logging
import re
import textwrap
from typing import Union, TYPE_CHECKING

import attr
import emoji as emoji_lib
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
from naff.models.discord.emoji import emoji_regex, PartialEmoji

from const import process_duration
from models.emoji import default_emoji
from models.events import PollCreate, PollClose, PollVote

if TYPE_CHECKING:
    pass

__all__ = ("deserialize_datetime", "PollData", "PollOption", "sanity_check")

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

    if Permissions.VIEW_CHANNEL not in channel_perms:
        await ctx.send("I can't view my messages in this channel", ephemeral=True)
        return False

    if Permissions.EMBED_LINKS not in channel_perms:
        await ctx.send(
            "I can't manage embeds in this channel, please give me the `Embed Links` permission", ephemeral=True
        )
        return False

    if Permissions.READ_MESSAGE_HISTORY not in channel_perms:
        await ctx.send(
            "I can't read message history in this channel, please give me the `Read Message History` permission",
            ephemeral=True,
        )
        return False

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

    if ctx.kwargs.get("vote_to_view", None) is True and ctx.kwargs.get("hide_results") is False:
        await ctx.send("You cannot enable `vote_to_view` and disable `hide_results`", ephemeral=True)
        return False
    return True


@attr.s(auto_attribs=True, on_setattr=[attr.setters.convert, attr.setters.validate])
class PollOption:
    text: str
    emoji: str
    voters: set[Snowflake_Type] = attr.ib(factory=set, converter=set)
    style: int = attr.ib(default=1)
    eliminated: bool = attr.ib(default=False)

    @property
    def inline_text(self) -> str:
        return f"{self.text[:15].strip()}" + ("..." if len(self.text) > 15 else "")

    def create_bar(self, total_votes, *, size: int = 12) -> str:
        show_counters = total_votes < 1000
        if total_votes != 0:
            percentage = len(self.voters) / total_votes
            filled_length = size * percentage

            prog_bar_str = "▓" * int(filled_length)

            if len(prog_bar_str) != size:
                prog_bar_str += "░" * (size - len(prog_bar_str))
        else:
            prog_bar_str = "░" * size
            return f"{prog_bar_str} - 0% (0 votes)"
        vote_string = f" ({len(self.voters):,} vote{'s' if len(self.voters) != 1 else ''})"
        return f"{prog_bar_str} - {percentage:.0%}{vote_string if show_counters else ''}"

    def has_voted(self, user_id: Snowflake_Type) -> bool:
        return user_id in self.voters

    def vote(self, author_id: Snowflake_Type) -> bool:
        if author_id not in self.voters:
            self.voters.add(author_id)
            return True
        else:
            self.voters.remove(author_id)
            return False

    @classmethod
    def deserialize(cls, data: dict) -> "PollOption":
        if isinstance(data, PollOption):
            return data

        if emoji := data.get("emoji"):
            if isinstance(emoji, dict):
                data["emoji"] = PartialEmoji.from_dict(emoji)
        return cls(**data)


@attr.s(auto_attribs=True, on_setattr=[attr.setters.convert, attr.setters.validate])
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

    poll_options: list[PollOption] = attr.ib(
        factory=list,
        converter=lambda options: [PollOption.deserialize(o) if not isinstance(o, PollOption) else o for o in options],
    )

    max_votes: int | None = attr.ib(default=None)
    voting_role: Snowflake_Type | None = attr.ib(default=None)
    hide_results: bool = attr.ib(default=False)
    vote_to_view: bool = attr.ib(default=False)
    anonymous: bool = attr.ib(default=False)
    open_poll: bool = attr.ib(default=False)
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
    deleted: bool = attr.ib(default=False)
    closed: bool = attr.ib(default=False)
    lock: asyncio.Lock = attr.ib(factory=asyncio.Lock)

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

    def get_colour(self) -> Color:
        if self.expired:
            return MaterialColors.GREY
        if self.colour in MaterialColors.__members__:
            return MaterialColors[self.colour]
        elif self.colour in BrandColors.__members__:
            return BrandColors[self.colour]
        else:
            return BrandColors.BLURPLE

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
            top_voted = sorted_votes[0]
            possible_ties = [o for o in sorted_votes if len(o.voters) == len(top_voted.voters)]
            if len(possible_ties) == 1:
                embed.add_field(
                    name="Highest Voted Option",
                    value=f"{sorted_votes[0].emoji} {sorted_votes[0].text} - {len(sorted_votes[0].voters)} votes ({len(sorted_votes[0].voters) / self.total_votes:.0%})",
                )
            else:
                embed.add_field(
                    name="Tied Highest Voted Options",
                    value="\n".join(
                        [
                            f"{o.emoji} {o.text} - {len(o.voters)} votes ({len(sorted_votes[0].voters) / self.total_votes:.0%})"
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
        hide_results = self.hide_results and not force_display
        if not self.proportional_results:
            for o in self.poll_options:
                name = textwrap.shorten(f"{o.emoji} {o.text}", width=EMBED_MAX_NAME_LENGTH)
                if not self.expired and hide_results:
                    fields.append(EmbedField(name=name, value="‏", inline=self.inline))
                else:
                    fields.append(EmbedField(name=name, value=o.create_bar(self.total_votes), inline=self.inline))
            return fields
        else:
            all_voters = {v for o in self.poll_options for v in o.voters}
            for o in self.poll_options:
                name = textwrap.shorten(f"{o.emoji} {o.text}", width=EMBED_MAX_NAME_LENGTH)

                if not self.expired and hide_results:
                    fields.append(EmbedField(name=name, value="‏", inline=self.inline))
                else:
                    fields.append(
                        EmbedField(
                            name=name,
                            value=o.create_bar(len(all_voters)),
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
        description.append(f"• {total_votes:,} vote{'s' if total_votes != 1 else ''}")

        if self.poll_type != "default":
            description.append(f"• {self.poll_type.title()} Poll")

        if self.single_vote:
            description.append("• One Vote Per User")
        if self.proportional_results:
            description.append("• Proportional Results")
        elif self.max_votes:
            description.append(f"• {self.max_votes} Votes Per User")
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

    def add_option(self, opt_name: str, _emoji: str | None = None) -> None:
        if len(self.poll_options) >= len(default_emoji):
            raise ValueError("Poll has reached max options")
        if not _emoji:
            if data := emoji_regex.findall(opt_name):
                parsed = tuple(filter(None, data[0]))
                if len(parsed) == 3:
                    _emoji = PartialEmoji(name=parsed[1], id=parsed[2], animated=True)
                    opt_name = opt_name.replace(str(_emoji), "")
                elif len(parsed) == 2:
                    _emoji = PartialEmoji(name=parsed[0], id=parsed[1], animated=False)
                    opt_name = opt_name.replace(str(_emoji), "")
                else:
                    _name = emoji_lib.emojize(opt_name, language="alias")
                    _emoji_list = emoji_lib.distinct_emoji_list(_name)
                    if _emoji_list:
                        _emoji = _emoji_list[0]
                        opt_name = emoji_lib.replace_emoji(_name, replace="")
            else:
                _emoji_list = emoji_lib.distinct_emoji_list(opt_name)
                if _emoji_list:
                    _emoji = _emoji_list[0]
                    opt_name = emoji_lib.replace_emoji(opt_name, replace="")

        self.poll_options.append(PollOption(opt_name.strip(), _emoji or default_emoji[len(self.poll_options)]))

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
        )

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
                    new_cls.add_option(o.strip().removeprefix("-"))

        if new_cls.vote_to_view and not new_cls.hide_results:
            new_cls.hide_results = True

        if attachment := kwargs.get("image"):
            new_cls.image_url = attachment.url

        if duration := kwargs.get("duration"):
            new_cls.expire_time = process_duration(duration)

        new_cls._client.dispatch(PollCreate(new_cls))

        return new_cls

    async def send(self, context: InteractionContext) -> Message:
        try:
            msg = await context.send(embeds=self.embed, components=[] if self.expired else self.get_components())
            self.parse_message(msg)
            if self.thread:
                thread = await msg.create_thread(self.title, reason=f"Poll created for {context.author.username}")
                thread_msg = await thread.send(components=self.get_components(disable=True))
                self.thread_message_id = thread_msg.id

            if self.expire_time:
                await context.bot.schedule_close(self)

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

    async def update_messages(self):
        self.reallocate_emoji()

        message = await self._client.cache.fetch_message(self.channel_id, self.message_id)
        await message.edit(embeds=self.embed, components=self.get_components())

        if self.thread:
            try:
                thread_msg = await self._client.cache.fetch_message(self.message_id, self.thread_message_id)
                await thread_msg.edit(components=self.get_components(disable=True))
            except Exception as e:
                log.error(f"Failed to update thread message: {e}")
                pass

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
        if self.expired:
            message = await self._client.cache.fetch_message(self.channel_id, self.message_id)
            await message.edit(components=self.get_components(disable=True))
            await ctx.send("This poll is closing - your vote will not be counted", ephemeral=True)
            return
        else:
            async with self.lock:
                if self.voting_role and self.voting_role != ctx.guild_id and not ctx.author.has_role(self.voting_role):
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
                        log.error(
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

                if self._vote(option, ctx.author):
                    log.info(f"Added vote to {self.message_id}")
                    embed = Embed(self.vote_added_text, color=BrandColors.GREEN)
                    embed.add_field("Option", f"⬆️ `{option.emoji} {option.text}`")
                    await ctx.send(embed=embed, ephemeral=True)
                else:
                    log.info(f"Removed vote from {self.message_id}")
                    embed = Embed(self.vote_removed_text, color=BrandColors.GREEN)
                    embed.add_field("Option", f"⬇️ `{option.emoji} {option.text}`")
                    await ctx.send(embed=embed, ephemeral=True)
                self._client.dispatch(PollVote(self, ctx.guild.id))

    def has_voted(self, user: Snowflake_Type) -> bool:
        user = to_snowflake(user)
        return any([option.has_voted(user) for option in self.poll_options])
