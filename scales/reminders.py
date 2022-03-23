import asyncio
from datetime import datetime, timedelta

from dpytools.errors import InvalidTimeString
from dpytools.parsers import to_timedelta, Trimmer
from typing import Optional
from dis_snek import slash_command, InteractionContext, Modal, InputText, TextStyles, Embed
from dis_snek.models import (
    Scale
)
from dis_snek.models.discord import color
import motor.motor_asyncio


def dumb_time(delta: timedelta) -> Optional[str]:
    if delta.total_seconds() <= 0:
        return "<:error:943118535922679879> I'm not sure what you expected, but I can't send reminders in the past"
    elif delta.total_seconds() <= (60):
        return "<:error:943118535922679879> You can't set a reminder for a minute or less from now. That wouldn't serve much of a purpose"


class Reminders(Scale):
    # Let's do some checking that our inputs aren't dumb

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
                    placeholder="Example: 1d 3h 46m to be reminded in 1day, 3hours and 46minutes",
                    style=TextStyles.SHORT,
                    required=True,
                )
            ],
        )
        await ctx.send_modal(modal)

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
            when_timestamp = f"<t:{when_timestamp[0]}:R>"
            client = motor.motor_asyncio.AsyncIOMotorClient(
                "",
                serverSelectionTimeoutMS=5000)
            db = client.reminders
            await db.all_reminders.insert_one({
                'user_id': ctx.author.id,
                'channel_id': ctx.channel.id,
                'next_time': when,
                'content': what,
                'recurrent_time': False,
                'done': False,
            })

            await modal_response.send(f"I'll remind you {when_timestamp} about {what}")
            # try:

            #     channel = self.bot.get_channel(954908602756395058)
            #     embed = Embed(title="<:success:943118562384547870> Suggestion received!",
            #                   color=color.Color.from_hex("#008000"),
            #                   description="Heyo! Thanks so much for your suggestion.\n"
            #                               "Suggestions that get accepted are awarded with one month of Nitro <:nitro:954911211131142165>")
            #     await modal_response.send(embeds=embed)
            #     embed = Embed(title=modal_response.responses.get("short_description"),
            #                   color=color.FlatUIColors.EMERLAND,
            #                   description=modal_response.responses.get("long_description")
            #                   )
            #     embed.add_field(name="Suggested by:", value=f"{ctx.author.user}\n{ctx.author.id}", inline=True)
            #     if ctx.guild:
            #         embed.add_field(name="Suggested from:", value=f"{ctx.guild.name}\n#{ctx.channel.name}", inline=True)
            #     else:
            #         embed.add_field(name="Suggested from:", value="DMs", inline=True)
            #     embed.set_thumbnail("https://share.boredman.net/a5cD3DUd.png")
            #     message = await channel.send(embeds=embed)
            #     await message.add_reaction("<:upvote:954937757711605780>")
            #     await message.add_reaction("<:downvote:954937757506109440>")
            # except:
            #     embed = Embed(
            #         title="<:error:943118535922679879> Something went wrong and I can't confirm your suggestion was saved",
            #         color=color.Color.from_hex("#FF0000"),
            #         description="Heyo! Thanks so much for your suggestion.\n"
            #                     "However, I'm not 100% sure it went through.\n"
            #                     "You could try again or use /msg-owner to contact the bot owner")

            # await modal_response.send(embeds=embed)
        except asyncio.TimeoutError:  # since we have a timeout, we can assume the user closed the modal
            return
def setup(bot):
    Reminders(bot)
