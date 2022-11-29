import datetime
import logging
from typing import TYPE_CHECKING

import attr
from naff.models import (
    Embed,
    MaterialColors,
    TimestampStyles,
    Timestamp,
)

from models._poll_base import BasePoll
from models.poll_option import PollOption

if TYPE_CHECKING:
    pass

__all__ = ("DefaultPoll",)

log = logging.getLogger("Inquiry")


@attr.s(auto_attribs=True, on_setattr=[attr.setters.convert, attr.setters.validate], kw_only=True)
class DefaultPoll(BasePoll):
    poll_type: str = attr.ib(default="default", init=False)

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

        if self.open_time and self.pending:
            description.append(f"• Opens {Timestamp.fromdatetime(self.open_time).format(TimestampStyles.RelativeTime)}")
        elif self.expire_time:
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
