import asyncio
import csv
import json
import logging
from io import BytesIO, StringIO
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np
import yaml
from naff import (
    InteractionContext,
    SlashCommand,
    File,
    Timestamp,
    Permissions,
    AutocompleteContext,
    slash_command,
    Embed,
    SlashCommandOption,
    SlashCommandChoice,
)

from extensions.shared import ExtensionBase, OPT_find_poll
from models.poll_default import DefaultPoll

if TYPE_CHECKING:
    from main import Bot

try:
    from yaml import CDumper as Dumper
except ImportError:
    from yaml import Dumper

__all__ = ("setup", "PollUtils")

log = logging.getLogger("Inquiry")


class PollUtils(ExtensionBase):
    bot: "Bot"

    def __init__(self, bot) -> None:
        self.view_poll.autocomplete("poll")(self.poll_autocomplete)
        self.export_text.autocomplete("poll")(self.poll_autocomplete)
        self.export_image.autocomplete("poll")(self.poll_autocomplete)

    def get_user(self, user_id) -> str:
        try:
            user = self.bot.get_user(user_id)
            return user.username
        except Exception as e:
            pass
        return user_id

    @staticmethod
    def poll_autocomplete_predicate(ctx: AutocompleteContext):
        def predicate(poll: DefaultPoll):
            if poll.anonymous:
                return False
            if poll.author_id == ctx.author.id:
                return True
            if ctx.author.has_permission(Permissions.MANAGE_MESSAGES):
                return True
            return False

        return predicate

    export = SlashCommand(name="export", description="Export a poll into various formats")

    def _csv_exporter(self, poll: DefaultPoll) -> StringIO:
        def rotate(input_list: list[list]) -> list[list]:
            expected_len = max(map(len, input_list))
            for sub_list in input_list:
                if len(sub_list) < expected_len:
                    sub_list.extend([None] * (expected_len - len(sub_list)))

            return list(zip(*input_list))  # type: ignore

        log.debug(f"Exporting {poll.message_id} to csv")
        buffer = []
        for option in poll.poll_options:
            buffer.append([option.text] + [self.get_user(v) for v in option.voters])

        buffer = rotate(buffer)
        f = StringIO()

        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerows(buffer)
        f.seek(0)
        return f

    def _json_exporter(self, poll: DefaultPoll) -> StringIO:
        log.debug(f"Exporting {poll.message_id} to json")
        buffer = {}
        for option in poll.poll_options:
            buffer[option.text] = [self.get_user(v) for v in option.voters]
        f = StringIO()

        json.dump(buffer, f)
        f.seek(0)
        return f

    def _yaml_exporter(self, poll: DefaultPoll) -> StringIO:
        log.debug(f"Exporting {poll.message_id} to yaml")
        buffer = {}
        for option in poll.poll_options:
            buffer[option.text] = [self.get_user(v) for v in option.voters]
        f = StringIO()

        yaml.dump(buffer, f, Dumper=Dumper)
        f.seek(0)
        return f

    def _bar_exporter(self, poll: DefaultPoll) -> BytesIO:
        log.debug(f"Exporting {poll.message_id} to bar graph")
        buffer = {}
        for option in poll.poll_options:
            buffer[option.text] = [self.get_user(v) for v in option.voters]
        f = BytesIO()

        arr = np.array([len(x) for x in buffer.values()])
        labels = list(buffer.keys())
        fig = plt.figure()
        plt.bar(labels, arr, width=0.4)
        plt.xlabel("Options")
        plt.ylabel("No. of Votes")
        plt.title(poll.title)
        plt.savefig(f, format="png")
        f.seek(0)
        return f

    def _pie_exporter(self, poll: DefaultPoll) -> BytesIO:
        log.debug(f"Exporting {poll.message_id} to pie chart")
        buffer = {}
        for option in poll.poll_options:
            buffer[option.text] = [self.get_user(v) for v in option.voters]
        f = BytesIO()

        arr = np.array([len(x) for x in buffer.values()])
        labels = list(buffer.keys())
        fig = plt.figure()
        plt.pie(arr, labels=labels)
        plt.title(poll.title)
        plt.savefig(f, format="png")
        f.seek(0)
        return f

    @export.subcommand(
        sub_cmd_name="text",
        sub_cmd_description="Export a poll into a text format",
        options=[
            OPT_find_poll,
            SlashCommandOption(
                "format",
                3,
                "The format to export the poll as",
                choices=[
                    SlashCommandChoice("csv  -- Spreadsheet formatting", "csv"),
                    SlashCommandChoice("yaml -- Human-readable formatting", "yaml"),
                    SlashCommandChoice("json -- Programmer formatting", "json"),
                ],
            ),
        ],
    )
    async def export_text(self, ctx: InteractionContext, poll: str, format: str) -> None:
        try:
            if poll := await self.process_poll_option(ctx, poll):
                if poll.anonymous:
                    await ctx.send("Anonymous polls cannot be exported", ephemeral=True)

                await ctx.defer()

                async with poll.lock:
                    await poll.cache_all_voters()
                    if all(len(opt.voters) == 0 for opt in poll.poll_options):
                        await ctx.send("No votes have been cast yet!")
                        return

                    match format:
                        case "csv":
                            file = await asyncio.to_thread(self._csv_exporter, poll)
                        case "json":
                            file = await asyncio.to_thread(self._json_exporter, poll)
                        case "yaml":
                            file = await asyncio.to_thread(self._yaml_exporter, poll)
                        case _:
                            await ctx.send(f"Unknown format {format}", ephemeral=True)
                            return

                    await ctx.send(file=File(file, file_name=f"{poll.title}.{format}"))
                    file.close()
                    return

        except Exception as e:
            log.error("Error exporting poll", exc_info=e)
        await ctx.send("That poll could not be exported", ephemeral=True)

    @export.subcommand(
        sub_cmd_name="image",
        sub_cmd_description="Export a poll into an image format",
        options=[
            OPT_find_poll,
            SlashCommandOption(
                "format",
                3,
                "The format to export the poll as",
                choices=[
                    SlashCommandChoice("Bar Chart", "bar"),
                    SlashCommandChoice("Pie Chart", "pie"),
                ],
            ),
        ],
    )
    async def export_image(self, ctx: InteractionContext, poll: str, format: str) -> None:
        try:
            if poll := await self.process_poll_option(ctx, poll):
                if poll.anonymous:
                    await ctx.send("Anonymous polls cannot be exported", ephemeral=True)

                await ctx.defer()

                async with poll.lock:
                    await poll.cache_all_voters()

                    if all(len(opt.voters) == 0 for opt in poll.poll_options):
                        await ctx.send("No votes have been cast yet!")
                        return

                    match format:
                        case "bar":
                            file = await asyncio.to_thread(self._bar_exporter, poll)
                        case "pie":
                            file = await asyncio.to_thread(self._pie_exporter, poll)
                        case _:
                            await ctx.send(f"Unknown format {format}", ephemeral=True)
                            return

                    await ctx.send(file=File(file, file_name=f"{poll.title}.png"))
                    file.close()
                    return

        except Exception as e:
            log.error("Error exporting poll", exc_info=e)
        await ctx.send("That poll could not be exported", ephemeral=True)

    @slash_command(
        "details",
        description="Display a more detailed view of a poll",
        options=[OPT_find_poll],
    )
    async def view_poll(self, ctx: InteractionContext, poll) -> None:
        if poll := await self.process_poll_option(ctx, poll):
            await ctx.defer()
            embed = Embed(title="Poll Details")
            embed.color = poll.get_colour()

            poll_config = []
            if poll.expire_time:
                poll_config.append(f"Expires {Timestamp.fromdatetime(poll.expire_time).format('R')}")
            if poll.single_vote:
                poll_config.append("Single vote only")
            elif poll.max_votes:
                poll_config.append(f"Max votes: {poll.max_votes}")
            if poll.hide_results:
                poll_config.append("Results hidden")
            if poll.open_poll:
                poll_config.append("Open poll")
            if poll.anonymous:
                poll_config.append("Anonymous poll")
            if poll.voting_role:
                poll_config.append(f"Voting role: <@{poll.voting_role}>")

            embed.add_field("Question", value=poll.title, inline=True)
            embed.add_field("Active", value="✅" if not poll.closed else "❌", inline=True)
            embed.add_field("Author", value=f"<@{poll.author_id}>", inline=True)

            if poll.description:
                embed.add_field("Description", value=poll.description)

            if poll.poll_options:
                embed.add_field("Choices", value="\n".join(f"{opt.emoji} {opt.text}" for opt in poll.poll_options))
            else:
                embed.add_field("Choices", value="No choices have been added yet!")

            embed.add_field(
                "Results",
                value="\n".join(
                    f"{opt.emoji} {opt.create_bar(poll.total_votes, size=24)} - {len(opt.voters):,}"
                    for opt in poll.poll_options
                ),
            )

            embed.add_field("Total Votes", value=f"{poll.total_votes:,}", inline=True)

            embed.add_field("Configuration", value="-" + "\n-".join(poll_config or ["Default"]))

            if poll.image_url:
                embed.set_image(url=poll.image_url)

            if author := await self.bot.fetch_member(poll.author_id, ctx.guild_id):
                embed.set_thumbnail(url=author.display_avatar.url)

            await ctx.send(embed=embed)

        else:
            await ctx.send("Unable to find the requested poll!")


def setup(bot: "Bot"):
    PollUtils(bot)
