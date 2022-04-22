from pathlib import Path

import dis_snek
import motor
from dis_snek import slash_command, InteractionContext, ChannelTypes, Embed, GuildText
from dis_snek.models import (
    Scale
)
from dis_snek.models.snek.application_commands import SlashCommandOption, OptionTypes, slash_option
from motor import motor_asyncio

mongoConnectionString = (Path(__file__).parent.parent / "mongo.txt").read_text().strip()

class Setup(Scale):
    @slash_command(
        name="setup",
        description="Setup Janet for your server",
        sub_cmd_name="modlog",
        sub_cmd_description="The channel you would like to log moderator actions to",
        scopes=[891613945356492890]
    )
    @slash_option(
        name="modlog_channel",
        description="The channel you would like to log moderator actions to",
        opt_type=OptionTypes.CHANNEL,
        channel_types=[ChannelTypes.GUILD_TEXT],
        required=True
    )
    async def setup_modlog_channel(self, ctx: InteractionContext, modlog_channel):
        # client = motor_asyncio.AsyncIOMotorClient(
        #         mongoConnectionString,
        #         serverSelectionTimeoutMS=5000
        # )
        # db = client.guilds.settings.find({'guild_id': ctx.guild.id})
        # await db.replace_one({'modlog_channel': modlog_channel.id})
        embed = Embed("ModLog channel updated", f"You've set your ModLog channel to {modlog_channel.mention}.")






def setup(bot):
    Setup(bot)
