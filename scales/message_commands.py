import contextlib
import io
import sys

import dis_snek
from dis_snek import Button, ButtonStyles, File
from dis_snek.models import (
    Scale,
    message_command,
    MessageContext,
    check,
    Context,
)

from scales.admin import is_owner


class MessageCommands(Scale):
    @message_command()
    @check(is_owner())
    async def owner_only(self, ctx: MessageContext):
        await ctx.send("You are the owner")

    @message_command()
    async def test_button(self, ctx: MessageContext):
        print("test button")
        await ctx.send("Danger Noodle!", components=Button(ButtonStyles.DANGER, "boop", custom_id="boop"))


def setup(bot):
    MessageCommands(bot)
