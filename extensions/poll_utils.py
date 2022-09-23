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
)
from thefuzz import process

from extensions.shared import ExtensionBase, OPT_find_poll
from models.poll import PollData

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
        self.export_csv.autocomplete("poll")(self.poll_autocomplete)
        self.export_json.autocomplete("poll")(self.poll_autocomplete)
        self.export_yaml.autocomplete("poll")(self.poll_autocomplete)
        self.export_pie.autocomplete("poll")(self.poll_autocomplete)
        self.export_bar.autocomplete("poll")(self.poll_autocomplete)
        self.view_poll.autocomplete("poll")(self.poll_autocomplete)

    def get_user(self, user_id) -> str:
        try:
            user = self.bot.get_user(user_id)
            return user.username
        except Exception as e:
            pass
        return user_id

    @staticmethod
    def poll_autocomplete_predicate(ctx: AutocompleteContext):
        def predicate(poll: PollData):
            if poll.author_id == ctx.author.id:
                return True
            if ctx.author.has_permission(Permissions.MANAGE_MESSAGES):
                return True
            return False

        return predicate

    export = SlashCommand(name="export", description="Export a poll into various formats")
    text = export.group(name="text", description="Export a poll into a text format")

    @text.subcommand(
        sub_cmd_name="csv",
        sub_cmd_description="Export a poll as a csv file",
        options=[OPT_find_poll],
    )
    async def export_csv(self, ctx: InteractionContext, poll) -> None:
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
                if all(len(opt.voters) == 0 for opt in poll.poll_options):
                    return await ctx.send("No votes have been cast yet!")
                file = await asyncio.to_thread(write_buffer, poll)
                await ctx.send(file=File(file, file_name=f"{poll.title}.csv"))
                file.close()

        else:
            await ctx.send("Unable to export the requested poll!")

    @text.subcommand(
        sub_cmd_name="json",
        sub_cmd_description="Export a poll as a json file",
        options=[OPT_find_poll],
    )
    async def export_json(self, ctx: InteractionContext, poll) -> None:
        if poll := await self.process_poll_option(ctx, poll):
            await ctx.defer()

            def write_buffer(_poll: PollData):
                log.debug(f"Exporting {_poll.message_id} to json")
                buffer = {}
                for option in poll.poll_options:
                    buffer[option.text] = [self.get_user(v) for v in option.voters]
                f = StringIO()

                json.dump(buffer, f)
                f.seek(0)
                return f

            async with poll.lock:
                if all(len(opt.voters) == 0 for opt in poll.poll_options):
                    return await ctx.send("No votes have been cast yet!")
                file = await asyncio.to_thread(write_buffer, poll)
                await ctx.send(file=File(file, file_name=f"{poll.title}.json"))
                file.close()

        else:
            await ctx.send("Unable to export the requested poll!")

    @text.subcommand(
        sub_cmd_name="yaml",
        sub_cmd_description="Export a poll as a yaml file",
        options=[OPT_find_poll],
    )
    async def export_yaml(self, ctx: InteractionContext, poll) -> None:
        if poll := await self.process_poll_option(ctx, poll):
            await ctx.defer()

            def write_buffer(_poll: PollData):
                log.debug(f"Exporting {_poll.message_id} to yaml")
                buffer = {}
                for option in poll.poll_options:
                    buffer[option.text] = [self.get_user(v) for v in option.voters]
                f = StringIO()

                yaml.dump(buffer, f, Dumper=Dumper)
                f.seek(0)
                return f

            async with poll.lock:
                if all(len(opt.voters) == 0 for opt in poll.poll_options):
                    return await ctx.send("No votes have been cast yet!")
                file = await asyncio.to_thread(write_buffer, poll)
                await ctx.send(file=File(file, file_name=f"{poll.title}.yaml"))
                file.close()

        else:
            await ctx.send("Unable to export the requested poll!")

    image = export.group(name="image", description="Export a poll to an image file")

    @image.subcommand(
        sub_cmd_name="pie",
        sub_cmd_description="Export a pie chart of the poll",
        options=[OPT_find_poll],
    )
    async def export_pie(self, ctx: InteractionContext, poll) -> None:
        if poll := await self.process_poll_option(ctx, poll):
            await ctx.defer()

            def write_buffer(_poll: PollData):
                log.debug(f"Exporting {_poll.message_id} to pie chart")
                buffer = {}
                for option in poll.poll_options:
                    buffer[option.text] = [self.get_user(v) for v in option.voters]
                f = BytesIO()

                arr = np.array([len(x) for x in buffer.values()])
                labels = list(buffer.keys())
                fig = plt.figure()
                plt.pie(arr, labels=labels)
                plt.title(_poll.title)
                plt.savefig(f, format="png")
                f.seek(0)
                return f

            async with poll.lock:
                if all(len(opt.voters) == 0 for opt in poll.poll_options):
                    return await ctx.send("No votes have been cast yet!")
                file = await asyncio.to_thread(write_buffer, poll)
                await ctx.send(file=File(file, file_name=f"{poll.title}.png"))
                file.close()

        else:
            await ctx.send("Unable to export the requested poll!")

    @image.subcommand(
        sub_cmd_name="bar",
        sub_cmd_description="Export a bar graph of the poll",
        options=[OPT_find_poll],
    )
    async def export_bar(self, ctx: InteractionContext, poll) -> None:
        if poll := await self.process_poll_option(ctx, poll):
            await ctx.defer()

            def write_buffer(_poll: PollData):
                log.debug(f"Exporting {_poll.message_id} to bar graph")
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
                plt.title(_poll.title)
                plt.savefig(f, format="png")
                f.seek(0)
                return f

            async with poll.lock:
                if all(len(opt.voters) == 0 for opt in poll.poll_options):
                    return await ctx.send("No votes have been cast yet!")
                file = await asyncio.to_thread(write_buffer, poll)
                await ctx.send(file=File(file, file_name=f"{poll.title}.png"))
                file.close()

        else:
            await ctx.send("Unable to export the requested poll!")

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
            if poll.hide_results:
                poll_config.append("Results hidden")
            if poll.open_poll:
                poll_config.append("Open poll")

            embed.add_field("Question", value=poll.title, inline=True)
            embed.add_field("Active", value="✅" if not poll.closed else "❌", inline=True)
            embed.add_field("Author", value=f"<@{poll.author_id}>", inline=True)

            if poll.description:
                embed.add_field("Description", value=poll.description)

            embed.add_field("Choices", value="\n".join(f"{opt.emoji} {opt.text}" for opt in poll.poll_options))

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
