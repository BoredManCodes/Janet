from typing import TYPE_CHECKING

from attr import define, field
from naff.api.events import BaseEvent


if TYPE_CHECKING:
    from models._poll_base import BasePoll
    from naff import InteractionContext


@define(slots=False)
class PollEvent(BaseEvent):
    poll: "BasePoll" = field()


@define(slots=False)
class PollCreate(PollEvent):
    ctx: "InteractionContext" = field()
    ...


@define(slots=False)
class PollClose(PollEvent):
    ...


@define(slots=False)
class PollVote(PollEvent):
    guild_id: int = field()
