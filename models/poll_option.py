from typing import TYPE_CHECKING

import attr
from naff import to_snowflake
from naff.models import (
    Snowflake_Type,
)
from naff.models.discord.emoji import PartialEmoji
from models.emoji import default_emoji

if TYPE_CHECKING:
    from models.poll import PollData

__all__ = ("PollOption",)


@attr.s(auto_attribs=True, on_setattr=[attr.setters.convert, attr.setters.validate])
class PollOption:
    text: str
    emoji: str
    voters: set[Snowflake_Type] = attr.ib(factory=set, converter=set)
    style: int = attr.ib(default=1)
    eliminated: bool = attr.ib(default=False)
    author_id: Snowflake_Type = None

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

    @classmethod
    def parse(cls, poll: "PollData", author: Snowflake_Type, opt_name: str, emoji: str | None = None) -> "PollOption":
        if not emoji:
            possible_emoji = opt_name.split(" ")[0]
            _emoji = PartialEmoji.from_str(possible_emoji)
            if _emoji:
                _emoji = _emoji.req_format
                opt_name = " ".join(opt_name.split(" ")[1:])

        return cls(opt_name.strip(), emoji or default_emoji[len(poll.poll_options)], author_id=to_snowflake(author))
