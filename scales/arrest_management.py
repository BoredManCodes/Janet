import dis_snek
from dis_snek import slash_command, slash_option, OptionTypes, InteractionContext, check
from dis_snek.models import (
    Scale
)


class ArrestManagement(Scale):

    @slash_command(
        name="arrest",
        scopes=[891613945356492890],
        description="Arrests a member"
    )
    @slash_option(
        name="user",
        description="The user to arrest",
        required=True,
        opt_type=OptionTypes.USER
    )
    @slash_option(
        name="reason",
        description="The reason for the arrest",
        required=True,
        opt_type=OptionTypes.STRING
    )
    async def arrest(self, ctx: InteractionContext, reason: None, user: dis_snek.Member = None):
        await ctx.send(f"{user.mention} has been arrested. Please wait.\n"
                       f"This shouldn't be more than a minute", ephemeral=False)
        mod_log = self.bot.get_channel(897765157940396052)
        police_station = self.bot.get_channel(866304038524813352)
        # whitelist = discord.utils.get(ctx.guild.roles, name='Whitelisted')
        # await user.remove_roles(whitelist)
        # arrestee = discord.utils.get(ctx.guild.roles, name='Arrestee')
        # muted = discord.utils.get(ctx.guild.roles, name='Muted')
        #
        # for member in ctx.guild.members:
        #     if arrestee in member.roles:
        #         await member.remove_roles(arrestee)
        # await user.add_roles(arrestee, muted)
        # await police_station.purge(limit=int(10000))
        # await police_station.set_permissions(discord.utils.get(ctx.guild.roles, name="Arrestee"), send_messages=True,
        #                                      read_messages=True, reason=reason)
        # await police_station.set_permissions(discord.utils.get(ctx.guild.roles, name="Moderator"), send_messages=True,
        #                                      read_messages=True, reason=reason)
        # await police_station.set_permissions(discord.utils.get(ctx.guild.roles, name="Administrator"),
        #                                      send_messages=True,
        #                                      read_messages=True, reason=reason)
        # await police_station.set_permissions(discord.utils.get(ctx.guild.roles, name="Adjudicator"), send_messages=True,
        #                                      read_messages=True, reason=reason)
        #
        # await mod_log.send(f'{ctx.author.display_name} cleared the <#866304038524813352> chat and arrested '
        #                    f'{user.display_name} for {reason}')
        # await police_station.send(f"{user.mention} you have been arrested for "
        #                           f"{reason}. Please stand-by\n"
        #                           f"```You do not have to say anything. But, it may harm your defence if you do not mention"
        #                           f" when questioned something which you later rely on in court. "
        #                           f"Anything you do say may be given in evidence. "
        #                           f"You have the right to have a lawyer present both during questioning and during court"
        #                           f" proceedings.```")


def setup(bot):
    ArrestManagement(bot)
