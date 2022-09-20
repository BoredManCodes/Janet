import asyncio
import datetime
import logging
import textwrap
from typing import Union

import attr
import emoji as emoji_lib
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
from naff.models.discord.emoji import emoji_regex, PartialEmoji

from const import process_duration
from models.emoji import default_emoji

__all__ = ("deserialize_datetime", "PollData", "PollOption", "sanity_check")

log = logging.getLogger("Poll")


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

    channel_perms = ctx.channel.permissions_for(ctx.guild.me)

    if Permissions.VIEW_CHANNEL not in channel_perms:
        await ctx.send("I can't view my messages in this channel", ephemeral=True)
        return False

    if Permissions.EMBED_LINKS not in channel_perms:
        await ctx.send(
            "I can't manage embeds in this channel, please give me the `Embed Links` permission", ephemeral=True
        )
        return False

    if ctx.kwargs.get("thread"):
        if not all(perm in channel_perms for perm in (Permissions.USE_PUBLIC_THREADS, Permissions.USE_PRIVATE_THREADS)):
            await ctx.send("I don't have the permissions to create threads in this channel", ephemeral=True)
            return False
        if isinstance(ctx.channel, ThreadChannel):
            await ctx.send("You cannot create a thread inside a thread!", ephemeral=True)
            return False
        if len(ctx.kwargs.get("title")) > 100:
            await ctx.send("Thread titles cannot be longer than 100 characters", ephemeral=True)
            return False

    return True


@attr.s(auto_attribs=True, on_setattr=[attr.setters.convert, attr.setters.validate])
class PollOption:
    text: str
    emoji: str
    voters: set[Snowflake_Type] = attr.ib(factory=set, converter=set)
    style: int = attr.ib(default=1)

    @property
    def inline_text(self) -> str:
        return f"{self.text[:15].strip()}" + ("..." if len(self.text) > 15 else "")

    def create_bar(self, total_votes, *, size: int = 12) -> str:
        if total_votes != 0:
            percentage = len(self.voters) / total_votes
            filled_length = size * percentage

            prog_bar_str = "▓" * int(filled_length)

            if len(prog_bar_str) != size:
                prog_bar_str += "░" * (size - len(prog_bar_str))
        else:
            prog_bar_str = "░" * size
            return f"{prog_bar_str} - 0%"
        return f"{prog_bar_str} - {percentage:.0%}"

    def vote(self, author_id: Snowflake_Type) -> bool:
        if author_id not in self.voters:
            self.voters.add(author_id)
            return True
        else:
            self.voters.remove(author_id)
            return False


@attr.s(auto_attribs=True, on_setattr=[attr.setters.convert, attr.setters.validate])
class PollData:
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
        converter=lambda options: [PollOption(**o) if not isinstance(o, PollOption) else o for o in options],
    )

    single_vote: bool = attr.ib(default=False)
    hide_results: bool = attr.ib(default=False)
    open_poll: bool = attr.ib(default=False)
    inline: bool = attr.ib(default=False)
    thread: bool = attr.ib(default=False)
    close_message: bool = attr.ib(default=False)

    colour: str = attr.ib(default="BLURPLE", converter=lambda x: x.upper())
    image_url: str = attr.ib(default=MISSING)

    _sent_close_message: bool = attr.ib(default=False)

    expire_time: datetime = attr.ib(default=MISSING, converter=deserialize_datetime)
    _expired: bool = attr.ib(default=False)
    closed: bool = attr.ib(default=False)
    lock: asyncio.Lock = attr.ib(factory=asyncio.Lock)

    def __dict__(self) -> dict:
        data = {
            k.removeprefix("_"): v
            for k, v in attr.asdict(self).items()
            if v != MISSING and not isinstance(v, asyncio.Lock)
        }
        data["poll_options"] = orjson.dumps(data.pop("poll_options")).decode()
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
        sorted_votes: list[PollOption] = sorted(self.poll_options, key=lambda x: len(x.voters), reverse=True)
        top_voted = sorted_votes[0]
        possible_ties = [o for o in sorted_votes if len(o.voters) == len(top_voted.voters)]

        embed.add_field(name="Poll Name", value=self.title, inline=False)

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
        embed.set_footer(text=f"Poll ID: {self.message_id}")
        return embed

    @property
    def embed(self) -> Embed:
        e = Embed(
            f"{self.title}" if self.title else "Poll:",
            "",
            color=self.get_colour() if not self.expired else MaterialColors.GREY,
        )
        total_votes = self.total_votes
        for i in range(len(self.poll_options)):

            option = self.poll_options[i]
            name = textwrap.shorten(f"{option.emoji} {option.text}", width=EMBED_MAX_NAME_LENGTH)
            if not self.expired and self.hide_results:
                e.add_field(name, "‏", inline=self.inline)
            else:
                e.add_field(
                    name,
                    option.create_bar(total_votes),
                    inline=self.inline,
                )

        if self.image_url:
            e.set_image(url=self.image_url)

        description = []
        if self.description:
            description.append(self.description)
        description.append(f"• {total_votes:,} vote{'s' if total_votes != 1 else ''}")

        if self.single_vote:
            description.append("• One Vote Per User")
        if self.hide_results:
            if self.expired:
                description.append("• Results were hidden until the poll ended")
            else:
                description.append("• Results are hidden until the poll ends")
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
        for i in range(len(self.poll_options)):
            buttons.append(
                Button(1, emoji=self.poll_options[i].emoji, custom_id=f"poll_option|{i}", disabled=self.expired),
            )
        if self.open_poll and len(self.poll_options) < len(default_emoji):
            buttons.append(
                Button(ButtonStyles.SUCCESS, emoji="\U00002795", custom_id="add_option", disabled=self.expired)
            )
        return spread_to_rows(*buttons)

    def add_option(self, opt_name: str, _emoji: str | None = None) -> None:
        if len(self.poll_options) >= len(default_emoji):
            raise ValueError("Poll has reached max options")
        if not _emoji:
            if data := emoji_regex.findall(opt_name):
                parsed = parsed = tuple(filter(None, data[0]))
                if len(parsed) == 3:
                    _emoji = PartialEmoji(name=parsed[1], id=parsed[2], animated=True)
                else:
                    _emoji = PartialEmoji(name=parsed[0], id=parsed[1])
                opt_name = opt_name.replace(str(_emoji), "")
            else:
                _emoji_list = emoji_lib.distinct_emoji_list(opt_name)
                if _emoji_list:
                    _emoji = _emoji_list[0]
                    opt_name = opt_name.replace(_emoji, "")

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
            title=kwargs.get("title"),
            description=kwargs.get("description", None),
            author_id=ctx.author.id,
            single_vote=kwargs.get("single_vote", False),
            hide_results=kwargs.get("hide_results", False),
            open_poll=kwargs.get("open_poll", False),
            inline=kwargs.get("inline", False),
            colour=kwargs.get("colour", "BLURPLE"),
            thread=kwargs.get("thread", False),
            channel_id=ctx.channel.id,
            guild_id=ctx.guild.id,
            author_name=ctx.author.display_name,
            author_avatar=ctx.author.avatar.url,
            close_message=kwargs.get("close_message", False),
        )

        if options := kwargs.get("options"):
            for o in options.split("\n-"):
                if o:
                    new_cls.add_option(o.strip().removeprefix("-"))

        if attachment := kwargs.get("image"):
            new_cls.image_url = attachment.url

        if duration := kwargs.get("duration"):
            new_cls.expire_time = process_duration(duration)

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

    async def send_close_message(self, client) -> None:
        if not self._sent_close_message:
            origin_message = await client.cache.fetch_message(self.channel_id, self.message_id)
            if origin_message:
                await origin_message.reply(embed=self.close_embed)
                self._sent_close_message = True

    async def update_messages(self, client):
        self.reallocate_emoji()

        message = await client.cache.fetch_message(self.channel_id, self.message_id)
        await message.edit(embeds=self.embed, components=self.get_components())

        if self.thread:
            try:
                thread_msg = await client.cache.fetch_message(self.message_id, self.thread_message_id)
                await thread_msg.edit(components=self.get_components(disable=True))
            except Exception as e:
                log.error(f"Failed to update thread message: {e}")
                pass
