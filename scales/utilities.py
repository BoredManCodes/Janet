import asyncio
import ipaddress
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from urllib import parse, request

import dis_snek
import motor
import pymongo
from dis_snek.api.events import GuildEmojisUpdate, GuildJoin, GuildLeft
from dis_snek.models.discord import color
from dis_snek.models.snek.application_commands import SlashCommandOption
from dis_snek import slash_command, InteractionContext, OptionTypes, Embed, Color, Modal, listen, Task, IntervalTrigger, \
    message_command, MessageContext
from dis_snek.models import (
    Scale
)
from motor import motor_asyncio
from pastypy import Paste

mongoConnectionString = (Path(__file__).parent.parent / "mongo.txt").read_text().strip()


class Utilities(Scale):
    @listen(GuildJoin)
    async def on_guild_join(self, event: GuildJoin):
        if self.bot.is_ready:
            # Send message to server owner
            # try:
            #     embed = Embed("Hi there!", "Thanks for inviting me.\nI am still in active development and as such am not a \"finished\" product.\n"
            #                                "I may not function exactly how I'm intended to, but I sure will try my best.\n"
            #                                "\nYou may use /setup in your server to configure me to your liking.")
            #     owner = await event.guild.fetch_owner()
            #     await owner.send(embeds=embed)
            # except:
            #     pass
            # Log guild join
            channel = self.bot.get_channel(940919818561912872)
            embed = Embed(title="<:RightArrow:943113486983110666> Joined new guild!",
                          color=color.FlatUIColors.CARROT)
            # if event.guild.icon is not None:
            #     try:
            #         embed.set_thumbnail(event.guild.icon.url)
            #     except Exception as e:
            #         print(e)
            # else:
            #     try:
            #         embed.set_thumbnail("https://share.boredman.net/LHHPDwim.png")
            #     except Exception as e:
            #         print(e)
            # if event.guild.banner is not None:
            #     embed.set_image(event.guild.banner)
            embed.add_field("Name", event.guild.name, inline=True)
            embed.add_field("Owner", event.guild.get_owner(), inline=True)
            embed.add_field("Created", event.guild.created_at, inline=False)
            if event.guild.description is not None:
                embed.add_field("Description", event.guild.description, inline=False)
            embed.add_field("Members", len([m for m in event.guild.members if not m.bot]), inline=True)
            embed.add_field("Bots", len([m for m in event.guild.members if m.bot]), inline=True)
            embed.add_field("Premium tier", event.guild.premium_tier, inline=False)
            embed.add_field("Premium boosters", len(event.guild.premium_subscribers), inline=True)
            await channel.send(embeds=embed)
            client = motor_asyncio.AsyncIOMotorClient(
                mongoConnectionString,
                serverSelectionTimeoutMS=5000
            )
            await client.guilds.settings.insert_one({
                'guild_name': event.guild.name,
                'guild_id': event.guild.id,
                'auto_quote': True,
                'modlog_enabled': False,
                'modlog_channel': None,
                'member_logging': False,
                'nickname_logging': False,
                'whitelist_role': None,
                'welcome_enabled': True,
                'welcome_channel': None,
                'welcome_messages': None,
                'leave_enabled': True,
                'leave_channel': None,
                'leave_messages': None,
                'moderator_roles': None,
                'dm_on_warns': True,
            })

    @listen(GuildLeft)
    async def on_guild_left(self, event: GuildLeft):
        channel = self.bot.get_channel(940919818561912872)
        embed = Embed(title="<:LeftArrow:943113444813594706> Left a guild!",
                      color=color.MaterialColors.RED)
        guild_names = []
        for guild in self.bot.guilds:
            guild_names.append(guild.name)
        embed.add_field(name="Guild name", value=str(set(self.guilds).difference(guild_names)).strip("{").strip("}").strip('"'))
        if event.guild.icon is not None:
            try:
                embed.set_thumbnail(event.guild.icon.url)
            except Exception as e:
                print(e)
        if event.guild.banner is not None:
            try:
                embed.set_image(event.guild.banner)
            except Exception as e:
                print(e)
        await channel.send(embeds=embed)

    @listen()
    async def on_ready(self):
        self.current_guilds.start()
        self.guilds = []
        for guild in self.bot.guilds:
            self.guilds.append(guild.name)

    @Task.create(IntervalTrigger(minutes=1))
    async def current_guilds(self):
        self.guilds = []
        for guild in self.bot.guilds:
            self.guilds.append(guild.name)

    @listen(GuildEmojisUpdate)
    async def emojis(self, event):
        if event.guild_id == 943106609897426965:
            channel = self.bot.get_channel(957164093716971540)
            await channel.purge(1000)
            await channel.send(f"{len(event.after)} emojis")
            for emoji in event.after:
                await channel.send(f"{emoji} {emoji.name} ({emoji.id})")

    @slash_command(
        name="msg-owner",
        description="Message the bot's owner. You will be blacklisted if you abuse this",
        options=[
            SlashCommandOption(
                name="message",
                description="What you want to send to the owner",
                type=OptionTypes.STRING,
                required=True
            )
        ]
    )
    async def msg_owner(self, ctx: InteractionContext, message):
        client = motor.motor_asyncio.AsyncIOMotorClient(
            mongoConnectionString,
            serverSelectionTimeoutMS=5000)
        blacklist = client.blacklist.blacklist.find({'user_id': ctx.author.id})
        blacklist = await blacklist.to_list(None)
        if blacklist:
            await ctx.send("You are blacklisted from this command for abusing it", ephemeral=True)
        else:
            await ctx.send("Message sent. Thanks.\nRemember abuse of this feature will get you blacklisted from it",
                           ephemeral=True)
            if ctx.guild:
                full_message = f"{ctx.author.user}({ctx.author.user.id}) in {ctx.guild.name} #{ctx.channel.name} sent\n\n{message}"
            else:
                full_message = f"{ctx.author.user}({ctx.author.id}) DM sent\n\n{message}"
            paste = Paste(content=full_message)
            paste.save("https://paste.trent-buckley.com")
            await self.bot.owner.send(f"{paste.url}.md")

    @message_command(name="blacklist")
    async def blacklist(self, ctx: MessageContext, user: int):
        if ctx.author == self.bot.owner:
            user = await self.bot.fetch_user(user)
            client = motor.motor_asyncio.AsyncIOMotorClient(
                mongoConnectionString,
                serverSelectionTimeoutMS=5000)
            blacklist = client.blacklist.blacklist.find({'user_id': user.id})
            blacklist = await blacklist.to_list(None)
            if blacklist:
                await ctx.send(f"{user.username} is already blacklisted\n\nRemoving them from it now")
                await client.blacklist.blacklist.delete_one({'user_id': user.id})

            else:
                await client.blacklist.blacklist.insert_one({
                    'user_id': user.id,
                })
                await ctx.send(f"Added {user.username} to the blacklist")

    @slash_command(
        name="suggestions",
        description="Add or view suggestions",
        sub_cmd_name="add",
        sub_cmd_description="Add a suggestion"
    )
    async def suggestion_add(self, ctx: InteractionContext):
        modal = Modal(
            title="So you think you can improve me?",
            components=[
                dis_snek.InputText(
                    label="Basic description for your suggestion",
                    custom_id="short_description",
                    placeholder="Some cool new idea",
                    style=dis_snek.TextStyles.SHORT,
                ),
                dis_snek.InputText(
                    label="Big description for your suggestion",
                    custom_id="long_description",
                    placeholder="Include examples if possible :D",
                    style=dis_snek.TextStyles.PARAGRAPH,
                )
            ],
        )
        await ctx.send_modal(modal)

        # now we can wait for the modal
        try:
            modal_response = await self.bot.wait_for_modal(modal, timeout=500)
            if len(modal_response.responses.get("short_description")) >= 512:
                await modal_response.send("<:error:943118535922679879> Your short description was too long.\n"
                                          "Please make a better **short** description")
                return
            try:
                channel = self.bot.get_channel(954908602756395058)
                embed = Embed(title="<:success:943118562384547870> Suggestion received!",
                              color=color.Color.from_hex("#008000"),
                              description="Heyo! Thanks so much for your suggestion.\n"
                                          "Suggestions that get accepted are awarded with one month of Nitro <:nitro:954911211131142165>")
                await modal_response.send(embeds=embed)
                embed = Embed(title=modal_response.responses.get("short_description"),
                              color=color.FlatUIColors.EMERLAND,
                              description=modal_response.responses.get("long_description")
                              )
                embed.add_field(name="Suggested by:", value=f"{ctx.author.user}\n{ctx.author.id}", inline=True)
                if ctx.guild:
                    embed.add_field(name="Suggested from:", value=f"{ctx.guild.name}\n#{ctx.channel.name}", inline=True)
                else:
                    embed.add_field(name="Suggested from:", value="DMs", inline=True)
                embed.set_thumbnail("https://share.boredman.net/a5cD3DUd.png")
                message = await channel.send(embeds=embed)
                await message.add_reaction("<:upvote:954937757711605780>")
                await message.add_reaction("<:downvote:954937757506109440>")
            except:
                embed = Embed(
                    title="<:error:943118535922679879> Something went wrong and I can't confirm your suggestion was saved",
                    color=color.Color.from_hex("#FF0000"),
                    description="Heyo! Thanks so much for your suggestion.\n"
                                "However, I'm not 100% sure it went through.\n"
                                "You could try again or use /msg-owner to contact the bot owner")
                await modal_response.send(embeds=embed)
        except asyncio.TimeoutError:  # since we have a timeout, we can assume the user closed the modal
            return


def setup(bot):
    Utilities(bot)
