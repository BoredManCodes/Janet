
from dis_snek import listen, Embed, Webhook, Color
from dis_snek.client.errors import CommandCheckFailure
from dis_snek.models import (
    Scale,
    message_command,
    MessageContext,
    check,
    Context,
)
from dis_snek.models.discord import color

from scales.admin import is_owner


class EventListener(Scale):
    @listen
    async def on_command_error(self, event, error):
        embed = Embed(title=f"**Error in command: {event.command}**", description=f"```\n{error}\n```")
        await event.send(embed=embed)
        raise error

    @listen
    async def on_member_update(self, before, after):
        print("member updated")
        if before.guild.id == 891613945356492890 and before.display_name != after.display_name:
            embed = Embed(title=f"Changed Name")
            embed.add_field(name='User', value=before.mention)
            embed.add_field(name='Before', value=before.display_name)
            embed.add_field(name='After', value=after.display_name)
            embed.set_thumbnail(url=after.avatar_url)
            channel = before.bot.get_channel(940919818561912872)
            await channel.send("boop")

def setup(bot):
    EventListener(bot)