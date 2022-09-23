import asyncio
import datetime
import logging
from typing import TYPE_CHECKING

from naff import (
    slash_command,
    InteractionContext,
    SlashCommandOption,
    OptionTypes,
    context_menu,
    CommandTypes,
    Embed,
    BrandColors,
    Button,
    ButtonStyles,
    ComponentContext,
)
from naff.api.events import Component

from extensions.shared import ExtensionBase, OPT_find_poll, OPT_find_option

if TYPE_CHECKING:
    from main import Bot

__all__ = ("setup", "EditPolls")

log = logging.getLogger("edit_poll")


class EditPolls(ExtensionBase):
    bot: "Bot"

    def __init__(self, bot) -> None:
        self.add_option.autocomplete("poll")(self.poll_autocomplete)
        self.remove_option.autocomplete("poll")(self.poll_autocomplete)
        self.close_poll.autocomplete("poll")(self.poll_autocomplete)
        self.delete_poll.autocomplete("poll")(self.poll_autocomplete)
        self.remove_option.autocomplete("option")(self.option_autocomplete)

    @slash_command("edit_poll", description="Edit a given poll")
    async def edit_poll(self, ctx: InteractionContext) -> None:
        """A dummy method for creating subcommands from"""
        ...

    @edit_poll.subcommand(
        "remove_option",
        sub_cmd_description="Remove an option from the poll",
        options=[OPT_find_poll, OPT_find_option],
    )
    async def remove_option(self, ctx: InteractionContext, poll, option) -> None:
        await ctx.defer(ephemeral=True)

        if poll := await self.process_poll_option(ctx, poll):
            if poll.author_id == ctx.author.id:
                message = await self.bot.cache.fetch_message(poll.channel_id, poll.message_id)
                if message:
                    if len(poll.poll_options) == 1 and not poll.open_poll:
                        return await ctx.send("Non-Open polls must have at least one option", ephemeral=True)
                    async with poll.lock:
                        for i in range(len(poll.poll_options)):
                            if poll.poll_options[i].text == option.replace("_", " "):
                                del poll.poll_options[i]

                                await poll.update_messages(self.bot)

                                await ctx.send(f"Removed `{option}` from `{poll.title}`")

                                break
                        else:
                            await ctx.send(f"Failed to remove `{option}` from `{poll.title}`")
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
    async def add_option(self, ctx: InteractionContext, poll, option) -> None:
        await ctx.defer(ephemeral=True)

        if poll := await self.process_poll_option(ctx, poll):
            if poll.author_id == ctx.author.id:

                message = await self.bot.cache.fetch_message(poll.channel_id, poll.message_id)
                if message:
                    async with poll.lock:
                        poll.add_option(option)

                        await poll.update_messages(self.bot)

                        await ctx.send(f"Added `{option}` to `{poll.title}`")
                    return
            else:
                await ctx.send("Only the author of the poll can edit it!")

    @edit_poll.subcommand("close", sub_cmd_description="Close a poll", options=[OPT_find_poll])
    async def close_poll(self, ctx: InteractionContext, poll) -> None:
        await ctx.defer(ephemeral=True)

        if poll := await self.process_poll_option(ctx, poll):
            if poll.author_id == ctx.author.id:
                async with poll.lock:
                    poll._expired = True

                    await poll.update_messages(self.bot)
                    await poll.send_close_message(self.bot)

                    await ctx.send(f"`{poll.title}` has been closed!")
                    await self.bot.send_thanks_message(ctx.channel.id)
            else:
                await ctx.send("Only the author of the poll can close it!")

    @context_menu("Close Poll", CommandTypes.MESSAGE)
    async def close_poll_context(self, ctx: InteractionContext):
        await ctx.defer(ephemeral=True)
        if poll := await self.bot.poll_cache.get_poll(ctx.target_id):
            if poll.author_id == ctx.author.id:
                async with poll.lock:
                    poll._expired = True

                    await poll.update_messages(self.bot)
                    await poll.send_close_message(self.bot)

                    await ctx.send(f"`{poll.title}` has been closed!")
                    await self.bot.send_thanks_message(ctx.channel.id)
            else:
                await ctx.send("Only the author of the poll can close it!")
        else:
            await ctx.send("This is not a poll!")

    @edit_poll.subcommand("delete", sub_cmd_description="Delete a poll", options=[OPT_find_poll])
    async def delete_poll(self, ctx: InteractionContext, poll) -> None:
        await ctx.defer()
        if poll := await self.process_poll_option(ctx, poll):
            if poll.author_id == ctx.author.id:
                embed = Embed(title="Delete Poll?", color=BrandColors.RED)
                embed.description = f"Are you sure you want to delete `{poll.title}`?\nThis action cannot be undone!"
                prompt = await ctx.send(
                    embed=embed,
                    components=[
                        Button(label="Delete Poll", style=ButtonStyles.DANGER, custom_id="delete"),
                        Button(label="Cancel", style=ButtonStyles.SUCCESS, custom_id="cancel"),
                    ],
                )
                try:
                    c: Component = await self.bot.wait_for_component(
                        messages=[prompt], timeout=20, check=lambda c: c.context.author.id == ctx.author.id
                    )
                    button_ctx = c.context
                    if button_ctx.custom_id == "delete":
                        await button_ctx.defer()

                        if not poll.closed:
                            try:
                                await self.bot.close_poll(poll.message_id)
                            except Exception:
                                pass

                        await self.bot.poll_cache.delete_poll(poll.message_id)
                        await button_ctx.send("Poll Deleted")
                        await prompt.edit(components=[])
                    else:
                        await prompt.edit(components=[])
                        await button_ctx.send("Cancelled")

                except asyncio.TimeoutError:
                    await prompt.edit(components=[])
                    await prompt.reply("Timed out!")
                except Exception as e:
                    await prompt.edit(components=[])
                    await prompt.reply(f"An error occurred: {e}")
                    log.error("An error occurred while deleting a poll", exc_info=e)
            else:
                await ctx.send("Only the author of the poll can delete it!")
        else:
            await ctx.send("This poll does not exist!")


def setup(bot) -> None:
    EditPolls(bot)
