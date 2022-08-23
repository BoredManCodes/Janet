import asyncio
import csv
import logging
from io import StringIO
from typing import TYPE_CHECKING

from naff import (
    InteractionContext,
    slash_command,
    File,
    Timestamp,
)
from thefuzz import process

from extensions.shared import ExtensionBase, OPT_find_poll
from models.poll import PollData

if TYPE_CHECKING:
    from main import Bot

__all__ = ("setup", "PollUtils")

log = logging.getLogger("Inquiry")


class PollUtils(ExtensionBase):
    bot: "Bot"

    def __init__(self, bot) -> None:
        self.export.autocomplete("poll")(self.poll_autocomplete)

    def get_user(self, user_id) -> str:
        try:
            user = self.bot.get_user(user_id)
            return user.username
        except Exception as e:
            pass
        return user_id

    async def poll_autocomplete(self, ctx: InteractionContext, poll) -> None:
        def predicate(_poll: PollData):
            if _poll.author_id == ctx.author.id:
                return True
            return False

        polls = await self.bot.poll_cache.get_polls_by_guild(ctx.guild_id)
        if polls:
            results = process.extract(ctx.input_text, {p.message_id: p.title for p in polls if predicate(p)}, limit=25)
            results = [await self.bot.poll_cache.get_poll_by_message(p[2]) for p in results if p[1] > 50]

            await ctx.send(
                [
                    {
                        "name": f"{p.title} ({Timestamp.from_snowflake(p.message_id).ctime()})",
                        "value": str(p.message_id),
                    }
                    for p in results
                ]
            )

        else:
            await ctx.send([])

    @slash_command("export", description="Export a poll as a csv file", options=[OPT_find_poll])
    async def export(self, ctx: InteractionContext, poll) -> None:
        if poll := await self.process_poll_option(ctx, poll):
            await ctx.defer()

            def write_buffer(_poll: PollData):
                def rotate(input_list: list[list]) -> list[list]:
                    expected_len = max(map(len, input_list))
                    for sub_list in input_list:
                        if len(sub_list) < expected_len:
                            sub_list.extend([None] * (expected_len - len(sub_list)))

                    return list(zip(*input_list))  # type: ignore

                log.debug(f"Exporting {_poll.message_id} to csv")
                buffer = []
                for option in poll.poll_options:
                    buffer.append([option.text] + [self.get_user(v) for v in option.voters])

                buffer = rotate(buffer)
                f = StringIO()

                writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                writer.writerows(buffer)
                f.seek(0)
                return f

            async with poll.lock:
                file = await asyncio.to_thread(write_buffer, poll)
                await ctx.send(file=File(file, file_name=f"{poll.title}.csv"))
                file.close()

        else:
            await ctx.send("Unable to export the requested poll!")


def setup(bot: "Bot"):
    PollUtils(bot)