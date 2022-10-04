from typing import TYPE_CHECKING

from attr import define
from naff.api.events import BaseEvent
from naff.client.utils import field

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
