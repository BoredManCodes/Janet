import contextlib
import io
from dis_snek.models import (
    Scale,
    message_command,
    MessageContext,
    check,
    Context,
)

from scales.admin import is_owner


class MessageCommandScale(Scale):
    @message_command()
    @check(is_owner())
    async def eval(self, ctx: MessageContext, *, code):
        async with ctx.typing():
            str_obj = io.StringIO()  # Retrieves a stream of data
            try:
                with contextlib.redirect_stdout(str_obj):
                    exec(code)
            except Exception as e:
                return await ctx.send(f"```{e.__class__.__name__}: {e}```")
            output = str_obj.getvalue()
            if len(output) < 1:
                output = "There was no output"
            await ctx.send(f'```py\n{output}```')