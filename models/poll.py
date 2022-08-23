import asyncio
import datetime

import attr
from naff import ModalContext, MISSING, ButtonStyles, Color, ActionRow
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

from const import process_duration
from models.emoji import default_emoji

__all__ = ("deserialize_datetime", "PollData", "PollOption")


def deserialize_datetime(date) -> datetime.datetime:
    if isinstance(date, str):
        return datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f")
    return date


@attr.s(auto_attribs=True, on_setattr=[attr.setters.convert, attr.setters.validate])
class PollOption:
    text: str
    emoji: str
    voters: set[Snowflake_Type] = attr.ib(factory=set, converter=set)
    style: int = attr.ib(default=1)

    @property
    def inline_text(self) -> str:
        return f"{self.text[:15].strip()}" + ("..." if len(self.text) > 15 else "")

    def create_bar(self, total_votes) -> str:
        prog_bar_str = ""
        prog_bar_length = 10
        percentage = 0
        if total_votes != 0:
            percentage = len(self.voters) / total_votes
            for i in range(prog_bar_length):
                if round(percentage, 1) <= 1 / prog_bar_length * i:
                    prog_bar_str += "░"
                else:
                    prog_bar_str += "▓"
        else:
            prog_bar_str = "░" * prog_bar_length
        prog_bar_str = prog_bar_str + f" {round(percentage * 100)}%"
        return prog_bar_str

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
    channel_id: Snowflake_Type = attr.ib(default=MISSING)
    message_id: Snowflake_Type = attr.ib(default=MISSING)
    guild_id: Snowflake_Type = attr.ib(default=MISSING)
    author_data: dict = attr.ib(default=MISSING)

    poll_options: list[PollOption] = attr.ib(
        factory=list,
        converter=lambda options: [PollOption(**o) if not isinstance(o, PollOption) else o for o in options],
    )

    single_vote: bool = attr.ib(default=False)
    hide_results: bool = attr.ib(default=False)
    open_poll: bool = attr.ib(default=False)
    inline: bool = attr.ib(default=False)
    colour: str = attr.ib(default="BLURPLE", converter=lambda x: x.upper())
    thread: bool = attr.ib(default=False)

    expire_time: datetime = attr.ib(default=MISSING, converter=deserialize_datetime)
    _expired: bool = attr.ib(default=False)
    closed: bool = attr.ib(default=False)
    lock: asyncio.Lock = attr.ib(factory=asyncio.Lock)

    def __dict__(self) -> dict:
        return {
            k.removeprefix("_"): v
            for k, v in attr.asdict(self).items()
            if v != MISSING and not isinstance(v, asyncio.Lock)
        }

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
    def embed(self) -> Embed:
        e = Embed(
            f"{self.title}" if self.title else "Poll:",
            "",
            color=self.get_colour() if not self.expired else MaterialColors.GREY,
        )
        total_votes = self.total_votes
        for i in range(len(self.poll_options)):

            option = self.poll_options[i]
            if not self.expired and self.hide_results:
                e.add_field(f"{option.emoji}", option.text, inline=self.inline)
            else:
                e.add_field(
                    f"{option.emoji} {option.text}",
                    option.create_bar(total_votes),
                    inline=self.inline,
                )
        description = [f"• {total_votes:,} vote{'s' if total_votes != 1 else ''}"]

        if self.single_vote:
            description.append("• One Vote Per User")
        if self.hide_results:
            if self.expired:
                description.append("• Results were hidden until the poll ended")
            else:
                description.append("• Results are hidden until the poll ends")
        if self.open_poll:
            description.append("• Open Poll - Anyone can add options")

        if self.expire_time:
            _c = "Closed" if self.expired else "Closes"
            description.append(
                f"• {_c} {Timestamp.fromdatetime(self.expire_time).format(TimestampStyles.RelativeTime)}"
            )

        e.description = "\n".join(description)

        if self.author_data:
            if "(" not in self.author_data["avatar_url"]:
                e.set_footer(
                    f'Asked by {self.author_data["name"]}',
                    icon_url=self.author_data["avatar_url"],
                )
            else:
                e.set_footer(f"Asked by {self.author_data['name']}")

        if self.expired:
            name = f' • Asked by {self.author_data["name"]}' if self.author_data else ""
            e.set_footer(f"This poll has ended{name}")

        return e

    @property
    def components(self) -> list[ActionRow]:
        if self.expired:
            return []
        buttons = []
        for i in range(len(self.poll_options)):
            buttons.append(
                Button(1, emoji=self.poll_options[i].emoji, custom_id=f"poll_option|{i}"),
            )
        if self.open_poll and len(self.poll_options) < len(default_emoji):
            buttons.append(Button(ButtonStyles.SUCCESS, emoji="\U00002795", custom_id="add_option"))
        return spread_to_rows(*buttons)

    def add_option(self, opt_name: str, emoji: str | None = None) -> None:
        if len(self.poll_options) >= len(default_emoji):
            raise ValueError("Poll has reached max options")
        self.poll_options.append(PollOption(opt_name.strip(), emoji or default_emoji[len(self.poll_options)]))

    def parse_message(self, msg: Message) -> None:
        self.channel_id = msg.channel.id
        self.message_id = msg.id

    @classmethod
    def from_ctx(cls, ctx: InteractionContext, m_ctx: ModalContext | None = None) -> "PollData":
        kwargs = ctx.kwargs
        if m_ctx:
            kwargs |= m_ctx.kwargs
        new_cls: "PollData" = cls(
            title=kwargs.get("title"),
            author_id=ctx.author.id,
            single_vote=kwargs.get("single_vote", False),
            hide_results=kwargs.get("hide_results", False),
            open_poll=kwargs.get("open_poll", False),
            inline=kwargs.get("inline", True),
            colour=kwargs.get("colour", "BLURPLE"),
            thread=kwargs.get("thread", False),
            channel_id=ctx.channel.id,
            guild_id=ctx.guild.id,
            author_data={
                "name": ctx.author.display_name,
                "avatar_url": ctx.author.avatar.url,
            },
        )

        if options := kwargs.get("options"):
            for o in options.split("\n-"):
                if o:
                    new_cls.add_option(o.strip().removeprefix("-"))

        if duration := kwargs.get("duration"):
            new_cls.expire_time = process_duration(duration)

        return new_cls

    async def send(self, context: InteractionContext) -> Message:
        try:
            msg = await context.send(embeds=self.embed, components=[] if self.expired else self.components)
            self.parse_message(msg)
            if self.thread:
                await msg.create_thread(self.title, reason=f"Poll created for {context.author.username}")
            return msg
        except Exception:
            raise
