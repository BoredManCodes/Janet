import dis_snek
from dis_snek import MessageContext, events
from dis_snek.api.events import MessageCreate, BaseEvent
from dis_snek.models import (
    Scale
)
import numpy as np
import Levenshtein as lv


def jaro(roles, dist, string):
    return map(lambda x: x<dist, map(lambda x: lv.jaro_winkler(string, x), roles))


class ReactionRoles(Scale):
    @dis_snek.slash_command(name="message_roles",
                            description="Set up some roles people can get from messages")
    @dis_snek.slash_option(name="message_link",
                           description="A link to the message you want to add roles to",
                           opt_type=dis_snek.OptionTypes.STRING,
                           required=True)
    @dis_snek.slash_option(name="role",
                           description="The role you'd like to give",
                           opt_type=dis_snek.OptionTypes.ROLE,
                           required=True)
    async def message_roles(self, ctx: dis_snek.InteractionContext, message_link: str, role: dis_snek.Role):
        await ctx.send(f"You entered {message_link}, and role {role.name}")
    # @dis_snek.message_command()
    # async def rrsetup(self, ctx: MessageContext):
    #     await ctx.send("Hi there. Let's get your reaction roles setup.\nPlease enter the role ID or the **exact** "
    #                    "name of the role. Alternatively you can mention the role")
    #     try:
    #         channel = self.bot.get_channel(891613945356492893)
    #         channel.send()
    #         role_names = []
    #         for role in ctx.guild.roles:
    #             role_names.append(role.name)
    #
    #         def is_author(m):
    #             return m.author == ctx
    #         msg = await self.bot.wait_for("Message", timeout=60, checks=is_author)
    #         print(msg)
    #         fuzzy = jaro(role_names, 5, msg)
    #         await ctx.send(str(fuzzy))
    #     except BaseException as e:
    #         await ctx.send(f"```\n{str(e)}```")
    #     # try:
    #     #     role = self.bot.get

def setup(bot):
    ReactionRoles(bot)
