import logging
from typing import TYPE_CHECKING

from naff import (
    Extension,
    slash_command,
    InteractionContext,
    Modal,
    ParagraphText,
)

from extensions.shared import get_options_list
from models.poll_elimination import EliminationPoll
from models.emoji import opinion_emoji
from models.poll_default import DefaultPoll

if TYPE_CHECKING:
    from main import Bot

__all__ = ("setup", "CreatePolls")

log = logging.getLogger("Inquiry")


class CreatePolls(Extension):
    def __init__(self, bot: "Bot") -> None:
        self.bot: "Bot" = bot

        self.set_extension_error(self.on_error)

    @slash_command(
        "poll",
        description="Create a poll",
        options=get_options_list(),
    )
    async def poll(self, ctx: InteractionContext) -> None:
        if not ctx.kwargs.get("preset_options"):
            modal = Modal(
                "Create a poll!",
                components=[
                    ParagraphText(
                        "Options: ",
                        placeholder="Start each option with a `-` ie: \n-Option 1\n-Option 2",
                        custom_id="options",
                    )
                ],
            )
            await ctx.send_modal(modal)

            m_ctx = await self.bot.wait_for_modal(modal, ctx.author)
            if not m_ctx.kwargs["options"].strip():
                return await m_ctx.send("You did not provide any options!", ephemeral=True)

            poll = await DefaultPoll.from_ctx(ctx, m_ctx)
            if not poll:
                return
            await m_ctx.send("Poll created!", ephemeral=True)
        else:
            preset = ctx.kwargs["preset_options"]
            poll = await DefaultPoll.from_ctx(ctx)
            if not poll:
                return
            log.debug(f"Creating poll from preset: {ctx.kwargs['preset_options']}")

            match preset.lower():
                case "boolean":
                    poll.add_option(ctx.author, "Yes", "✅")
                    poll.add_option(ctx.author, "No", "❌")
                case "week":
                    options = [
                        "Monday",
                        "Tuesday",
                        "Wednesday",
                        "Thursday",
                        "Friday",
                        "Saturday",
                        "Sunday",
                    ]
                    for opt in options:
                        poll.add_option(ctx.author, opt)
                case "month":
                    options = [
                        "January",
                        "February",
                        "March",
                        "April",
                        "May",
                        "June",
                        "July",
                        "August",
                        "September",
                        "October",
                        "November",
                        "December",
                    ]
                    for opt in options:
                        poll.add_option(ctx.author, opt)
                case "opinion":
                    poll.add_option(ctx.author, "Agree", opinion_emoji[0])
                    poll.add_option(ctx.author, "Neutral", opinion_emoji[1])
                    poll.add_option(ctx.author, "Disagree", opinion_emoji[2])
                case "rating":
                    for i in range(0, 10):
                        poll.add_option(ctx.author, str(i + 1))
                case "rating_5":
                    for i in range(0, 5):
                        poll.add_option(ctx.author, str(i + 1))

        if not poll:
            return

        msg = await poll.send(ctx)
        await self.bot.set_poll(poll)

    @slash_command(
        "poll_inline",
        description="Create a poll with inline options; this is to help with using emoji in polls",
        options=get_options_list(inline_options=True),
    )
    async def poll_inline(self, ctx: InteractionContext) -> None:
        raw_options = ctx.kwargs["options"]
        ctx.kwargs["options"] = [o.strip() for o in raw_options.split("|")]

        poll = await DefaultPoll.from_ctx(ctx)
        if not poll:
            return
        msg = await poll.send(ctx)
        await self.bot.set_poll(poll)

    @slash_command(
        "poll_blank",
        description="An open poll with no starting options",
        options=get_options_list(open_poll=False),
    )
    async def prefab_blank(self, ctx: InteractionContext) -> None:
        poll = await DefaultPoll.from_ctx(ctx)
        if not poll:
            return

        poll.open_poll = True
        msg = await poll.send(ctx)
        await self.bot.set_poll(poll)

    @slash_command(
        "poll_elimination",
        description="A poll where options are removed when they're voted for",
        options=get_options_list(
            anonymous=False,
            open_poll=False,
            proportional=False,
            view_results=False,
            show_option_author=False,
            preset=False,
        ),
    )
    async def prefab_elimination(self, ctx: InteractionContext) -> None:
        modal = Modal(
            "Create a poll!",
            components=[
                ParagraphText(
                    "Options: ",
                    placeholder="Start each option with a `-` ie: \n-Option 1\n-Option 2",
                    custom_id="options",
                )
            ],
        )
        await ctx.send_modal(modal)

        m_ctx = await self.bot.wait_for_modal(modal, ctx.author)
        if not m_ctx.kwargs["options"].strip():
            return await m_ctx.send("You did not provide any options!", ephemeral=True)

        poll = await EliminationPoll.from_ctx(ctx, m_ctx)
        if not poll:
            return

        msg = await poll.send(ctx)
        await self.bot.set_poll(poll)
        await m_ctx.send("To close the poll, react to it with 🔴", ephemeral=True)

    async def on_error(self, error: Exception, ctx: InteractionContext, *args, **kwargs) -> None:
        await ctx.send(f"**Error:** {error}", ephemeral=True)
        log.error(f"Error in {ctx.invoke_target}: {error}", exc_info=error)


def setup(bot) -> None:
    CreatePolls(bot)
