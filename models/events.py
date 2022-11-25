from typing import TYPE_CHECKING

from attr import define, field
from naff.api.events import BaseEvent

if TYPE_CHECKING:
    from models.poll_default import DefaultPoll
    from naff import InteractionContext


@define(slots=False)
class PollEvent(BaseEvent):
    poll: "DefaultPoll" = field()


@define(slots=False)
class PollCreate(PollEvent):
    ctx: "InteractionContext" = field()
    ...


@define(slots=False)
class PollClose(PollEvent):
    ...


@define(slots=False)
class PollVote(PollEvent):
    poll: "DefaultPoll" = field()
    guild_id: int = field()
