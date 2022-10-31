import asyncio
import inspect
from io import StringIO

import orjson
from naff import (
    Extension,
    slash_command,
    InteractionContext,
    Button,
    ButtonStyles,
    slash_option,
    OptionTypes,
    File,
    MISSING,
    to_snowflake,
)
from naff.models.naff import checks

from models.poll import PollData


class Dev(Extension):
    def __init__(self, _):
        self.add_ext_check(checks.is_owner())

    @slash_command("dev", description="Developer only commmands", scopes=[1013821165191581756, 985991455074050078])
    async def dev(self, ctx):
        ...

    @dev.subcommand("purge", sub_cmd_description="Purge the database of any guilds the bot is not in")
    async def purge(self, ctx: InteractionContext):
        await ctx.defer()

        guild_ids = [guild.id for guild in self.bot.guilds]

        predicted_deletions = await self.bot.poll_cache.db.fetchval(
            "SELECT COUNT(*) FROM polls.poll_data WHERE NOT (guild_id = ANY($1))", guild_ids
        )
        if predicted_deletions == 0:
            return await ctx.send("No polls to delete")
        affected_guild_ids = await self.bot.poll_cache.db.fetch(
            f"SELECT guild_id FROM polls.poll_data WHERE NOT (guild_id = ANY($1))", guild_ids
        )
        affected_guild_ids = set(guild["guild_id"] for guild in affected_guild_ids)

        file = StringIO()
        file.write(str(affected_guild_ids))
        file.seek(0)

        message = await ctx.send(
            f"This will delete {predicted_deletions} polls from the database, are you sure you want to continue?",
            components=[
                Button(label="Yes", style=ButtonStyles.DANGER, custom_id="yes"),
                Button(label="No", style=ButtonStyles.PRIMARY, custom_id="no"),
            ],
            file=File(file, file_name="affected_guild_ids.txt"),
        )

        try:
            out = await self.bot.wait_for_component(
                messages=[message], check=lambda c: c.ctx.author.id == ctx.author.id
            )
            button_ctx = out.ctx

            if button_ctx.custom_id == "yes":
                await button_ctx.defer()
                await message.edit(components=[])
                await self.bot.poll_cache.db.execute(
                    "DELETE FROM polls.poll_data WHERE NOT (guild_id = ANY($1))", guild_ids
                )
                await button_ctx.send(f"Deleted {predicted_deletions} polls from the database")
            else:
                await button_ctx.send("Aborted Purge")
                await message.edit(components=[])

        except asyncio.TimeoutError:
            return await message.edit("Timed out", components=[])

    @dev.subcommand("get", sub_cmd_description="Get a poll from the database")
    @slash_option("poll_id", "The id of the poll to get", opt_type=OptionTypes.STRING, required=True)
    async def get(self, ctx: InteractionContext, poll_id: int):
        await ctx.defer()

        poll = await self.bot.poll_cache.get_poll(poll_id)

        if not poll:
            return await ctx.send("Poll not found")

        file = StringIO()
        file.write(orjson.dumps((poll.to_dict()), option=orjson.OPT_INDENT_2).decode())
        file.seek(0)

        await ctx.send(file=File(file, file_name="poll.json"))

    @dev.subcommand("delete", sub_cmd_description="Delete a poll from the database")
    @slash_option("poll_id", "The id of the poll to delete", opt_type=OptionTypes.STRING, required=True)
    async def delete(self, ctx: InteractionContext, poll_id: int):
        await ctx.defer()

        poll = await self.bot.poll_cache.get_poll(poll_id)

        if not poll:
            return await ctx.send("Poll not found")

        await self.bot.poll_cache.delete_poll(poll_id)
        await ctx.send(f"Poll ({poll.title}) deleted")

    @dev.subcommand("reopen", sub_cmd_description="Reopen a poll")
    @slash_option("poll_id", "The id of the poll to reopen", opt_type=OptionTypes.STRING, required=True)
    async def reopen(self, ctx: InteractionContext, poll_id: int):
        await ctx.defer()

        poll: PollData = await self.bot.poll_cache.get_poll(poll_id)

        if not poll:
            return await ctx.send("Poll not found")

        poll.expire_time = MISSING
        poll._expired = False
        poll.closed = False
        poll._sent_close_message = False

        await poll.update_messages()

        await ctx.send(f"Poll ({poll.title}) reopened")

    @dev.subcommand("lookup", sub_cmd_description="Search through the cache for a specified ID")
    @slash_option("id", "The id to search for", opt_type=OptionTypes.STRING, required=True)
    @slash_option("all", "Find all matching objects", opt_type=OptionTypes.BOOLEAN, required=False)
    async def lookup(self, ctx: InteractionContext, id: str, all: bool = False):
        await ctx.defer()

        found: bool = False
        caches = [
            c[0]
            for c in inspect.getmembers(self.bot.cache, predicate=lambda x: isinstance(x, dict))
            if not c[0].startswith("__")
        ]

        for cache in caches:
            _c = getattr(self.bot.cache, cache)
            for obj in _c.values():
                if getattr(obj, "id", None) == to_snowflake(id):
                    file = StringIO()
                    if hasattr(obj, "__dict__") or hasattr(obj, "to_dict"):
                        json = obj.to_dict() if hasattr(obj, "to_dict") else obj.__dict__
                        file = StringIO()
                        file.write(orjson.dumps(json, option=orjson.OPT_INDENT_2).decode())
                    else:
                        file.write(str(obj))
                    file.seek(0)
                    await ctx.send(f"Found `{id}` in `{cache}`", file=File(file, file_name="object.json"))
                    found = True
                    if not all:
                        return

        if not found:
            await ctx.send(f"No object found with `{id}`")


def setup(bot):
    Dev(bot)
