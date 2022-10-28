from typing import TYPE_CHECKING

from attr import define, field
from naff.api.events import BaseEvent

if TYPE_CHECKING:
    from models.poll import PollData


@define(slots=False)
class PollEvent(BaseEvent):
    poll: "PollData" = field()


@define(slots=False)
class PollCreate(PollEvent):
    ...


@define(slots=False)
class PollClose(PollEvent):
    ...


@define(slots=False)
class PollVote(PollEvent):
    poll: "PollData" = field()
    guild_id: int = field()
