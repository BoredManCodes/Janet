import asyncio
import uuid
from configparser import RawConfigParser
from datetime import datetime, timedelta
from pathlib import Path

import pymongo
from bson import ObjectId
from dis_snek.client.errors import NotFound
from dis_snek.ext.paginators import Paginator
from dis_snek.models.snek import tasks
from dpytools.errors import InvalidTimeString
from dpytools.parsers import to_timedelta, Trimmer
from typing import Optional
from dis_snek import slash_command, InteractionContext, Modal, InputText, TextStyles, Embed, Task, IntervalTrigger, \
    listen, ButtonStyles
from dis_snek.models import (
    Scale
)
from dis_snek.models.discord import color
import motor.motor_asyncio


mongoConnectionString = (Path(__file__).parent.parent / "mongo.txt").read_text().strip()


def dumb_time(delta: timedelta) -> Optional[str]:
    if delta.total_seconds() <= 0:
        return "<:error:943118535922679879> I'm not sure what you expected, but I can't send reminders in the past"
    # elif delta.total_seconds() <= (60):
    #     return "<:error:943118535922679879> You can't set a reminder for a minute or less from now. That wouldn't serve much of a purpose"


class Reminders(Scale):
    @listen()
    async def on_ready(self):
        self.check_reminders.start()

    # So here we are going to define the commands for reminder adding.
    # We will worry later about actually reminding
    @slash_command(
        name="reminders",
        description="Manage your reminders",
        sub_cmd_name="add",
        sub_cmd_description="Add a reminder"
    )
    async def reminder_add(self, ctx: InteractionContext):
        modal = Modal(
            title="Create a reminder",
            components=[
                InputText(
                    label="What do you want to be reminded about?",
                    custom_id="reminder_content",
                    placeholder="Example: set up patreon roles",
                    style=TextStyles.PARAGRAPH,
                    required=True,
                    max_length=3000
                ),
                InputText(
                    label="When do you want to be reminded?",
                    custom_id="reminder_time",
                    placeholder="Example: 1d 3h to be reminded in 1day and 3hours",
                    style=TextStyles.SHORT,
                    required=True,
                )
            ],
        )
        await ctx.send_modal(modal)
        client = motor.motor_asyncio.AsyncIOMotorClient(
            mongoConnectionString,
            serverSelectionTimeoutMS=5000)
        db = client.reminders
        # now we can wait for the modal
        try:
            modal_response = await self.bot.wait_for_modal(modal, timeout=500)
            try:
                time = to_timedelta(modal_response.responses.get("reminder_time"))
            except InvalidTimeString as e:
                await modal_response.send("<:error:943118535922679879> That doesn't look like a valid time. Please enter the time in the format of <number>[s|m|h|d|w]", ephemeral=True)
                return
            if dumb_time_string := dumb_time(time):
                return await modal_response.send(dumb_time_string)

            what = modal_response.responses.get("reminder_content")
            now = datetime.now()
            when = now + time
            when_timestamp = str(when.timestamp()).split(".")
            when_timestamp = int(when_timestamp[0])
            when_relative = f"<t:{when_timestamp}:R>"
            when_absolute = f"<t:{when_timestamp}:F>"
            if ctx.guild is not None:
                await db.all_reminders.insert_one({
                    'user_id': ctx.author.id,
                    'channel_id': ctx.channel.id,
                    'time': when_timestamp,
                    'content': what,
                    'done': False,
                    'uuid': str(uuid.uuid4()),
                    'dm': False
                })
            else:
                await db.all_reminders.insert_one({
                    'user_id': ctx.author.id,
                    'time': when_timestamp,
                    'content': what,
                    'done': False,
                    'uuid': str(uuid.uuid4()),
                    'dm': True
                })
            embed = Embed(title="<a:reminder:956707969318412348> Reminder added",
                          color=color.FlatUIColors.CARROT,
                          description=f"I'll remind you {when_absolute}({when_relative})\nAbout: {what}")
            await modal_response.send(embeds=embed)
        except asyncio.TimeoutError:  # since we have a timeout, we can assume the user closed the modal
            return

    @slash_command(
        name="reminders",
        description="Manage your reminders",
        sub_cmd_name="list",
        sub_cmd_description="List your current reminders"
    )
    async def reminder_list(self, ctx: InteractionContext):
        try:
            client = motor.motor_asyncio.AsyncIOMotorClient(
                mongoConnectionString,
                serverSelectionTimeoutMS=5000)
            reminders = client.reminders.all_reminders.find({'user_id': ctx.author.id}).sort('time', pymongo.ASCENDING)
            reminders = await reminders.to_list(None)
            embeds = []
            count = 0
            for reminder in reminders:
                count += 1
                embeds.append(Embed(title=f"<a:reminder:956707969318412348> Reminder {count}",
                                    description=f"Content: ```\n{reminder['content']}```\nDue: <t:{reminder['time']}:F>"
                                                f"(<t:{reminder['time']}:R>)",
                                    color=color.FlatUIColors.CARROT))
            paginator = Paginator.create_from_embeds(self.bot, *embeds, timeout=300)
            paginator.wrong_user_message = "<:error:943118535922679879> These aren't your reminders"
            paginator.callback_button_emoji = "<:garbagebin:957162939201224744>"
            paginator.show_callback_button = True
            if len(reminders) > 1:
                await paginator.send(ctx)
            elif len(reminders) == 1:
                paginator.show_back_button = False
                paginator.show_first_button = False
                paginator.show_last_button = False
                paginator.show_next_button = False
                await paginator.send(ctx)
            elif len(reminders) == 0:
                embed = Embed(title="<a:reminder:956707969318412348> You have no reminders",
                              color=color.FlatUIColors.CARROT)
                await ctx.send(embeds=embed)

        except BaseException as e:
            embed = Embed(title=f"<:error:943118535922679879> Something went wrong", description=f"```\n{str(e)}```", color=color.FlatUIColors.CARROT)
            await ctx.send(embeds=embed)
            pass

    @Task.create(IntervalTrigger(seconds=5))
    async def check_reminders(self):
        now = str(datetime.now().timestamp()).split(".")
        now = int(now[0])
        client = motor.motor_asyncio.AsyncIOMotorClient(
            mongoConnectionString,
            serverSelectionTimeoutMS=5000)
        db = client.reminders
        reminders = db.all_reminders.find({'done': False}).sort('time', pymongo.ASCENDING)
        reminders = await reminders.to_list(length=None)
        for reminder in reminders:
            if now >= reminder['time']:
                if not reminder['dm']:
                    channel = self.bot.get_channel(reminder['channel_id'])
                else:
                    channel = self.bot.get_user(reminder['user_id'])
                await channel.send(f"<@{reminder['user_id']}>,")
                embed = Embed(title="<a:reminder:956707969318412348> Here's your reminder",
                              color=color.FlatUIColors.CARROT,
                              description=f"You asked me to remind you <t:{reminder['time']}:R>\nAbout: {reminder['content']}")
                await channel.send(embeds=embed)
                await db.all_reminders.delete_one({'uuid': reminder['uuid']})

def setup(bot):
    Reminders(bot)
