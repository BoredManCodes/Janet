from dis_snek import listen, Task, IntervalTrigger
from dis_snek.models import (
    Scale
)
import os
from millify import millify

class UpdatingChannels(Scale):
    # Will worry about my guild's updating channels for now
    @listen()
    async def on_ready(self):
        self.bored_channels.start()

    @Task.create(IntervalTrigger(minutes=5))
    async def bored_channels(self):
        if "nt" not in os.name:  # don't update channels if running as dev bot
            amount_total_members = 0
            amount_total_bots = 0
            for guild in self.bot.guilds:
                await guild.chunk_guild()
                amount_total_members += len([m for m in guild.members if not m.bot])
                amount_total_bots += len([m for m in guild.members if m.bot])
            total_members = self.bot.get_channel(958308205405028372)
            total_bots = self.bot.get_channel(959956677073965116)
            total_guilds = self.bot.get_channel(958308257917710347)
            guild_members = self.bot.get_channel(958308290876543048)
            bored_guild = self.bot.get_guild(891613945356492890)
            if total_members.name != f"Total Members: {millify(amount_total_members)}":
                await total_members.edit(name=f"Total Members: {millify(amount_total_members)}")
            if total_bots.name != f"Total Bots: {millify(amount_total_bots)}":
                await total_bots.edit(name=f"Total Bots: {millify(amount_total_bots)}")
            if total_guilds.name != f"Total Guilds: {millify(len(self.bot.guilds))}":
                await total_guilds.edit(name=f"Total Guilds: {millify(len(self.bot.guilds))}")
            if guild_members.name != f"Members Here: {millify(bored_guild.member_count)}":
                await guild_members.edit(name=f"Members Here: {millify(bored_guild.member_count)}")


def setup(bot):
    UpdatingChannels(bot)

