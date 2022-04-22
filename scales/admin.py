import asyncio
from pathlib import Path

import aiohttp
import dis_snek.api.events
import motor
from motor import motor_asyncio
from dis_snek import listen, Embed, slash_command, InteractionContext, slash_option, OptionTypes, Modal, InputText, \
    TextStyles
from dis_snek.client.errors import CommandCheckFailure
from dis_snek.models import (
    Scale,
    message_command,
    MessageContext,
    check,
    Context,
)


def is_owner():
    """
    Is the author the owner of the bot.

    parameters:
        coro: the function to check
    """

    async def check(ctx: Context) -> bool:
        return ctx.author.id == 324504908013240330

    return check


mongoConnectionString = (Path(__file__).parent.parent / "mongo.txt").read_text().strip()


class AdminCommands(Scale):
    @slash_command(name="welcome",
                   description="Configure the welcome message system",
                   sub_cmd_name="message",
                   sub_cmd_description="Send `help` for possible placeholders")
    @slash_option(name="format",
                  description="Send `help` for possible placeholders",
                  opt_type=OptionTypes.STRING,
                  required=True)
    async def welcome_msg(self, ctx: InteractionContext, format: str):
        if dis_snek.Permissions.MANAGE_GUILD in ctx.author.guild_permissions:
            if format == "help":
                placeholders = "Possible placeholders:\n" \
                               "`%userName%`, `%userID%`, `%userMention%`, `%userDiscriminator%`, `%memberCount%`\n" \
                               "Use `\\n` to insert a new line"
                embed = Embed(title="Welcome message", description=placeholders)
                await ctx.send(embeds=embed)
            else:
                string = format.replace("%userName%",
                                        ctx.author.username).replace("%userID%",
                                        str(ctx.author.id)).replace("%userMention%",
                                        ctx.author.mention).replace("%userDiscriminator%",
                                        f"#{ctx.author.discriminator}").replace("%memberCount%",
                                        str(ctx.guild.member_count)).replace("\\n", "\n")
                client = motor.motor_asyncio.AsyncIOMotorClient(
                    mongoConnectionString,
                    serverSelectionTimeoutMS=5000)
                await client.guilds.welcome_messages.replace_one({
                    'guild_id': ctx.guild_id
                }, {
                    'guild_id': ctx.guild_id, 'welcome_message': string
                },
                    upsert=True)
                await ctx.send("Welcome message set, sending test message now")
                embed = Embed(description=string)
                embed.set_thumbnail(url=ctx.author.display_avatar.url)
                await ctx.guild.system_channel.send(embeds=embed)
        else:
            await ctx.send(
                f"You are missing permissions to manage this guild, contact the guild owner, {ctx.guild.get_owner()}")

    @listen()
    async def on_member_add(self, event: dis_snek.api.events.MemberAdd):
        print("Member joined")
        guilds = [891613945356492890]
        if event.guild_id in guilds:
            client = motor.motor_asyncio.AsyncIOMotorClient(
                mongoConnectionString,
                serverSelectionTimeoutMS=5000)
            try:
                database = client.guilds.welcome_messages.find({'guild_id': event.guild_id})
                message = await database.to_list(length=None)
                string = str(message[0])
                string = string.replace("%userName%",
                                        event.member.user.username).replace("%userID%",
                                        str(event.member.user.id)).replace("%userMention%",
                                        event.member.user.mention).replace("%userDiscriminator%",
                                        f"#{event.member.user.discriminator}").replace("%memberCount%",
                                        str(event.guild.member_count))
                embed = Embed(description=string)
                embed.set_thumbnail(url=event.member.display_avatar.url)
                await event.guild.system_channel.send(embeds=embed)
            except Exception as e:
                print(e)

    @listen()
    async def on_member_update(self, event: dis_snek.api.events.MemberUpdate):
        if event.before.pending and not event.after.pending:
            if event.guild_id == 950158101892464691:  # If tiktoker server
                embed = Embed(":tada:", f"**Hey <@{event.after.user.id}>!**\n\n"
                                        f"Welcome to the server a few things you might want to check out is <#950158287763013682> for "
                                        f"recent announcements. Or if you haven't already checked out the bot, go post "
                                        f"a TikTok in <#950158196583059526>. Have a nice stay!")
                await event.guild.system_channel.send(embeds=embed)


def setup(bot):
    AdminCommands(bot)
