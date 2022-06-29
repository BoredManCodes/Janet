from typing import TYPE_CHECKING

from naff import (
    Extension,
    slash_command,
    InteractionContext,
    SlashCommandOption,
    OptionTypes,
    AutocompleteContext,
    Timestamp,
    to_snowflake,
)
from thefuzz import fuzz

from models.poll import PollData

if TYPE_CHECKING:
    from main import Bot

OPT_find_poll = SlashCommandOption(
    name="poll",
    description="The poll to edit",
    type=OptionTypes.STRING,
    required=True,
    autocomplete=True,
)

OPT_find_option = SlashCommandOption(
    name="option",
    description="The option to remove",
    type=OptionTypes.STRING,
    required=True,
    autocomplete=True,
)


class EditPolls(Extension):
    bot: "Bot"

    async def process_poll_option(self, ctx: InteractionContext, poll: str):
        try:
            poll = await self.bot.get_poll(ctx.guild_id, to_snowflake(poll))
        except AttributeError:
            pass
        finally:
            if not isinstance(poll, PollData):
                await ctx.send("Unable to find the requested poll!")
                return None
            return poll

    @slash_command("edit_poll", description="Edit a given poll")
    async def edit_poll(self, ctx: InteractionContext) -> None:
        """A dummy method for creating subcommands from"""
        ...

    @edit_poll.subcommand(
        "remove_option",
        sub_cmd_description="Remove an option from the poll",
        options=[OPT_find_poll, OPT_find_option],
    )
    async def remove_option(self, ctx: InteractionContext, poll, option):
        await ctx.defer(ephemeral=True)

        if poll := await self.process_poll_option(ctx, poll):
            if poll.author_id == ctx.author.id:
                message = await self.bot.cache.fetch_message(
                    poll.channel_id, poll.message_id
                )
                if message:
                    async with poll.lock:
                        for i in range(len(poll.poll_options)):
                            if poll.poll_options[i].text == option.replace("_", " "):
                                del poll.poll_options[i]
                                await message.edit(
                                    embeds=poll.embed, components=poll.components
                                )
                                await ctx.send(
                                    f"Removed `{option}` from `{poll.title}`"
                                )
                                break
                        else:
                            await ctx.send(
                                f"Failed to remove `{option}` from `{poll.title}`"
                            )
                    return
            else:
                return await ctx.send("Only the author of the poll can edit it!")

    @edit_poll.subcommand(
        "add_option",
        sub_cmd_description="Add an option to the poll",
        options=[
            OPT_find_poll,
            SlashCommandOption(
                name="option",
                description="The option to add",
                type=OptionTypes.STRING,
                required=True,
            ),
        ],
    )
    async def add_option(self, ctx: InteractionContext, poll, option):
        await ctx.defer(ephemeral=True)

        if poll := await self.process_poll_option(ctx, poll):
            if poll.author_id == ctx.author.id:

                message = await self.bot.cache.fetch_message(
                    poll.channel_id, poll.message_id
                )
                if message:
                    async with poll.lock:
                        poll.add_option(option)
                        await message.edit(
                            embeds=poll.embed, components=poll.components
                        )
                        await ctx.send(f"Added `{option}` to `{poll.title}`")
                    return
            else:
                await ctx.send("Only the author of the poll can edit it!")

    @edit_poll.subcommand(
        "close", sub_cmd_description="Close a poll", options=[OPT_find_poll]
    )
    async def close_poll(self, ctx: InteractionContext, poll):
        await ctx.defer(ephemeral=True)

        if poll := await self.process_poll_option(ctx, poll):
            if poll.author_id == ctx.author.id:
                async with poll.lock:
                    poll._expired = True
                    message = await self.bot.cache.fetch_message(
                        poll.channel_id, poll.message_id
                    )
                    await message.edit(embeds=poll.embed, components=[])
                    await self.bot.delete_poll(ctx.guild_id, poll.message_id)
                    await ctx.send(f"`{poll.title}` has been closed!")
            else:
                await ctx.send("Only the author of the poll can close it!")

    # @edit_poll.subcommand(
    #     "rename_option",
    #     sub_cmd_description="Rename an option in the poll",
    #     options=[OPT_find_poll, OPT_find_option],
    # )
    # async def rename_option(self, ctx: InteractionContext):
    #     ...
    #
    # @edit_poll.subcommand(
    #     "rename_poll", sub_cmd_description="Rename the poll", options=[OPT_find_poll]
    # )
    # async def rename_poll(self, ctx: InteractionContext):
    #     ...

    # @rename_poll.autocomplete("poll")
    # @rename_option.autocomplete("poll")
    @add_option.autocomplete("poll")
    @remove_option.autocomplete("poll")
    @close_poll.autocomplete("poll")
    async def poll_autocomplete(self, ctx: AutocompleteContext, **kwargs):
        polls = self.bot.polls.get(ctx.guild_id)
        if polls:
            polls = [
                p
                for p in polls.values()
                if p.author_id == ctx.author.id and not p.expired
            ]
            polls = sorted(
                polls,
                key=lambda x: fuzz.partial_ratio(x.title, ctx.input_text),
                reverse=True,
            )[:25]

            await ctx.send(
                [
                    {
                        "name": f"{p.title} ({Timestamp.from_snowflake(p.message_id).ctime()})",
                        "value": str(p.message_id),
                    }
                    for p in polls
                ]
            )

        else:
            await ctx.send([])

    @remove_option.autocomplete("option")
    # @rename_option.autocomplete("option")
    async def option_autocomplete(self, ctx: AutocompleteContext, **kwargs):
        poll = await self.bot.get_poll(ctx.guild_id, to_snowflake(kwargs.get("poll")))
        if poll:
            p_options = list(poll.poll_options)
            p_options = sorted(
                p_options,
                key=lambda x: fuzz.partial_ratio(x.text, ctx.input_text),
                reverse=True,
            )[:25]

            await ctx.send([p.text for p in p_options])

        else:
            await ctx.send([])


def setup(bot):
    EditPolls(bot)
