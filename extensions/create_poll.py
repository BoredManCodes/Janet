from typing import TYPE_CHECKING

from naff import (
    SlashCommandOption,
    OptionTypes,
    SlashCommandChoice,
    MaterialColors,
    Extension,
    slash_command,
    InteractionContext,
    Modal,
    ParagraphText,
)

from models.poll import PollData, PollOption

if TYPE_CHECKING:
    from main import Bot

colours = sorted(
    [MaterialColors(c).name.title() for c in MaterialColors]
    + [
        "Blurple",
        "Fuchsia",
        "White",
        "Black",
    ]
)

def_options = [
    SlashCommandOption(
        "title", OptionTypes.STRING, "The title for your poll", required=True
    ),
    SlashCommandOption(
        "colour",
        OptionTypes.STRING,
        "Choose the colour of the embed (default 'blurple')",
        choices=[SlashCommandChoice(c.replace("_", " "), c) for c in colours],
        required=False,
    ),
    SlashCommandOption(
        "duration",
        OptionTypes.INTEGER,
        "Automatically close the poll after this many minutes",
        required=False,
    ),
    SlashCommandOption(
        "single_vote",
        OptionTypes.BOOLEAN,
        "Only allow a single vote per user (default False)",
        required=False,
    ),
    SlashCommandOption(
        "thread",
        OptionTypes.BOOLEAN,
        "Create a thread attached to this poll.",
        required=False,
    ),
    SlashCommandOption(
        "inline",
        OptionTypes.BOOLEAN,
        "Make options appear inline, in the embed (default True)",
        required=False,
    ),
]


class CreatePolls(Extension):
    bot: "Bot"

    @slash_command(
        "poll",
        description="Create a poll",
        options=def_options,
    )
    async def poll(self, ctx: InteractionContext):
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
    async def prefab_boolean(self, ctx: InteractionContext):
        await ctx.defer()

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
    async def prefab_week(self, ctx: InteractionContext):
        await ctx.defer()

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
    async def prefab_opinion(self, ctx: InteractionContext):
        await ctx.defer()

        poll = PollData.from_ctx(ctx)
        poll.add_option("Agree", "✅")
        poll.add_option("Neutral", "➖")
        poll.add_option("Disagree", "❌")

        msg = await poll.send(ctx)
        await self.bot.set_poll(ctx.guild_id, msg.id, poll)


def setup(bot):
    CreatePolls(bot)
