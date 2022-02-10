from dis_snek import context_menu, CommandTypes, InteractionContext
from dis_snek.models import (
    Scale
)


class ContextScale(Scale):
    @context_menu(name="User menu", context_type=CommandTypes.USER)
    async def user_context_menu(self, ctx: InteractionContext):
        await ctx.send("boop")


def setup(bot):
    ContextScale(bot)
