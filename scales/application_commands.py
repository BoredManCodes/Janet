from dis_snek import Embed, Color
from dis_snek.models import (
    Scale
)


class ApplicationCommands(Scale):
    async def has_perms(self, ctx):  # Check that a user has one of the roles to manage the bot
        for b in ctx.author.roles:
            if b.id in RJD["perms"]:
                return True

        # Slash commands don't have a message object
        try:
            name = ctx.message.author.display_name
        except:
            name = ctx.author.display_name
        try:
            icon = ctx.message.author.avatar_url
        except:
            icon = ctx.author.avatar_url
        embed = Embed(title="We ran into an error",
                              description="You don't have permissions to manage this bot's functions",
                              color=Color.from_hex("ff0000"))
        embed.set_footer(text=f"Caused by {name}", icon_url=icon)
        await ctx.send(embed=embed)
        return False


def setup(bot):
    ApplicationCommands(bot)