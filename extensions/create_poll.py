from typing import TYPE_CHECKING

from naff import (
    Extension,
    slash_command,
    InteractionContext,
    Modal,
    ParagraphText,
)

from extensions.shared import def_options
from models.emoji import opinion_emoji
from models.poll import PollData

if TYPE_CHECKING:
    from main import Bot

__all__ = ("setup", "CreatePolls")


class CreatePolls(Extension):
    def __init__(self, bot: "Bot") -> None:
        self.bot: "Bot" = bot

        self.set_extension_error(self.on_error)

    @slash_command(
        "poll",
        description="Create a poll",
        options=def_options,
    )
    async def poll(self, ctx: InteractionContext) -> None:
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

        poll = PollData.from_ctx(ctx, m_ctx)

        msg = await poll.send(ctx)
        await self.bot.set_poll(ctx.guild_id, msg.id, poll)
        await m_ctx.send("To close the poll, react to it with 🔴", ephemeral=True)

    @slash_command("poll_prefab", description="Create a poll using pre-set options")
    async def poll_prefab(self, ctx: InteractionContext) -> None:
        """A dummy method for creating subcommands from"""
        ...

    @poll_prefab.subcommand(
        "boolean",
        sub_cmd_description="A poll with yes and no options",
        options=def_options,
    )
    async def prefab_boolean(self, ctx: InteractionContext) -> None:
        poll = PollData.from_ctx(ctx)
        poll.add_option("Yes", "✅")
        poll.add_option("No", "❌")

        msg = await poll.send(ctx)
        await self.bot.set_poll(ctx.guild_id, msg.id, poll)

    @poll_prefab.subcommand(
        "week",
        sub_cmd_description="A poll with options for each day of the week",
        options=def_options,
    )
    async def prefab_week(self, ctx: InteractionContext) -> None:
        poll = PollData.from_ctx(ctx)

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
            poll.add_option(opt)

        msg = await poll.send(ctx)
        await self.bot.set_poll(ctx.guild_id, msg.id, poll)

    @poll_prefab.subcommand(
        "opinion",
        sub_cmd_description="A poll with agree, neutral, and disagree options",
        options=def_options,
    )
    async def prefab_opinion(self, ctx: InteractionContext) -> None:
        poll = PollData.from_ctx(ctx)
        poll.add_option("Agree", opinion_emoji[0])
        poll.add_option("Neutral", opinion_emoji[1])
        poll.add_option("Disagree", opinion_emoji[2])

        msg = await poll.send(ctx)
        await self.bot.set_poll(ctx.guild_id, msg.id, poll)

    async def on_error(self, error: Exception, ctx: InteractionContext, *args, **kwargs) -> None:
        await ctx.send(f"**Error:** {error}", ephemeral=True)


def setup(bot) -> None:
    CreatePolls(bot)
