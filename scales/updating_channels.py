from dis_snek import listen, Task, IntervalTrigger
from dis_snek.models import (
    Scale
)


class UpdatingChannels(Scale):
    # Will worry about my guild's updating channels for now
    @listen()
    async def on_ready(self):
        self.bored_channels.start()

    @Task.create(IntervalTrigger(minutes=5))
    async def bored_channels(self):
        amount_total_members = 0
        for guild in self.bot.guilds:
            amount_total_members += guild.member_count
        total_members = self.bot.get_channel(958308205405028372)
        total_guilds = self.bot.get_channel(958308257917710347)
        guild_members = self.bot.get_channel(958308290876543048)
        bored_guild = self.bot.get_guild(891613945356492890)
        await total_members.edit(name=f"Total Members: {amount_total_members}")
        await total_guilds.edit(name=f"Total Guilds: {len(self.bot.guilds)}")
        await guild_members.edit(name=f"Members Here: {bored_guild.member_count}")


def setup(bot):
    UpdatingChannels(bot)
