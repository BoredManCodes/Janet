import asyncio
import ipaddress
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from urllib import parse, request

import dis_snek
from dis_snek.api.events import GuildEmojisUpdate, GuildJoin, GuildLeft
from dis_snek.models.discord import color
from dis_snek.models.snek.application_commands import SlashCommandOption
from dis_snek import slash_command, InteractionContext, OptionTypes, Embed, Color, Modal, listen
from dis_snek.models import (
    Scale
)
from motor import motor_asyncio
from pastypy import Paste

mongoConnectionString = (Path(__file__).parent.parent / "mongo.txt").read_text().strip()


class Utilities(Scale):
    @listen(GuildJoin)
    async def guild_join(self, event: GuildJoin):
        # Log guild join
        if self.bot.is_ready:
            channel = self.bot.get_channel(940919818561912872)
            embed = Embed(title="<:Announce:943113367424479232> Joined new guild!",
                          color=color.FlatUIColors.CARROT)
            if event.guild.icon is not None:
                embed.set_thumbnail(event.guild.icon.url)
            if event.guild.banner is not None:
                embed.set_image(event.guild.banner)
            embed.add_field("Name", event.guild.name, inline=True)
            embed.add_field("Owner", event.guild.get_owner(), inline=True)
            embed.add_field("Created", event.guild.created_at, inline=False)
            if event.guild.description is not None:
                embed.add_field("Description", event.guild.description, inline=False)
            embed.add_field("Members", len(event.guild.members), inline=True)
            embed.add_field("Premium tier", event.guild.premium_tier, inline=True)
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

    # @listen(GuildLeft)
    # async def guild_left(self, event: GuildLeft):
    #     # Log guild leave
    #     print("boop")
    # print(event.guild)
    # channel = self.bot.get_channel(940919818561912872)
    # embed = Embed(title="<:Announce:943113367424479232> Left a guild!",
    #               color=color.MaterialColors.RED)
    # if event.guild.icon is not None:
    #     embed.set_thumbnail(event.guild.icon.url)
    # if event.guild.banner is not None:
    #     embed.set_image(event.guild.banner)
    # embed.add_field("Name", event.guild.name, inline=True)
    # embed.add_field("Owner", event.guild.get_owner(), inline=True)
    # embed.add_field("Created", event.guild.created_at, inline=False)
    # if event.guild.description is not None:
    #     embed.add_field("Description", event.guild.description, inline=False)
    # embed.add_field("Members", len(event.guild.members), inline=True)
    # embed.add_field("Premium tier", event.guild.premium_tier, inline=True)
    # embed.add_field("Premium boosters", len(event.guild.premium_subscribers), inline=True)
    # await channel.send(embeds=embed)

    @listen(GuildEmojisUpdate)
    async def emojis(self, event):
        if event.guild_id == 943106609897426965:
            channel = self.bot.get_channel(957164093716971540)
            await channel.purge(1000)
            await channel.send(f"{len(event.after)} emojis")
            for emoji in event.after:
                await channel.send(f"{emoji} {emoji.name} ({emoji.id})")

    @slash_command(name="ip",
                   description="Displays information on the given IP",
                   options=[
                       SlashCommandOption(
                           name="address",
                           description="The IP address you want to check",
                           type=OptionTypes.STRING,
                           required=True
                       )])
    async def ip(self, ctx: InteractionContext, address=None):
        if address is None:
            embed = Embed(title="We ran into an error", description="You forgot to add an IP",
                          color=Color.from_hex("ff0000"))
            embed.set_footer(text=f"Caused by {ctx.author.display_name}", icon_url=ctx.author.avatar_url)
            await ctx.send(embed=embed)
            return

        try:
            # This will return an error if it's not a valid IP. Saves me doing input validation
            ipaddress.ip_address(address)
            message = await ctx.send("https://cdn.discordapp.com/emojis/783447587940073522.gif")
            # os.system(f"ping -c 1  {address}")
            try:
                ping = subprocess.check_output(["ping", "-c", "1", address]).decode('utf-8')
            except subprocess.CalledProcessError:
                ping = "Host appears down, or not answering ping requests"
            os.system(f"nmap  {address} -oG nmap.grep")
            process = subprocess.Popen(['./nmap.sh'],
                                       stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            stdout, stderr = process.communicate()
            three = stdout.decode('utf-8').replace('///', '')
            two = three.replace('//', ' ')
            one = two.replace('/', ' ').replace('      1 ', '')
            url = 'https://neutrinoapi.net/ip-info'
            params = {
                'user-id': "BoredManSwears",
                'api-key': "ghwsjEpDP31gv0tzrz732ShPNBVIf2KZ9bFGkJkw4IERSsxA",
                'ip': address,
                'reverse-lookup': True
            }
            postdata = parse.urlencode(params).encode()
            req = request.Request(url, data=postdata)
            response = request.urlopen(req)
            result = json.loads(response.read().decode("utf-8"))
            url = 'https://neutrinoapi.net/ip-probe'
            params = {
                'user-id': "BoredManSwears",
                'api-key': "ghwsjEpDP31gv0tzrz732ShPNBVIf2KZ9bFGkJkw4IERSsxA",
                'ip': address,
                'reverse-lookup': True
            }
            postdata = parse.urlencode(params).encode()
            req = request.Request(url, data=postdata)
            response = request.urlopen(req)
            probe = json.loads(response.read().decode("utf-8"))
            embed = Embed(title="IP lookup", description=f"Lookup details for {address}",
                          color=Color.from_hex("ff0000"))
            embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.avatar_url)
            try:
                embed.add_field(name="Location", value=f"{result['city']}\n{result['region']}, {result['country']}",
                                inline=True)
            except:
                print(probe)
            if not result['hostname'] == '':
                embed.add_field(name="Hostname", value=str(result['hostname']), inline=True)
            if not result['host-domain'] == '':
                embed.add_field(name="Host Domain", value=str(result['host-domain']), inline=True)
            embed.add_field(name="Maps Link",
                            value=f"https://maps.google.com/?q={result['latitude']},{result['longitude']}", inline=True)
            embed.add_field(name="Provider", value=f"{probe['provider-description']}", inline=True)
            if probe['is-vpn']:
                embed.add_field(name="Is VPN?", value=f"Yes {probe['vpn-domain']}", inline=True)
            elif not probe['is-vpn']:
                embed.add_field(name="Is VPN?", value=f"No", inline=True)
            if probe['is-hosting']:
                embed.add_field(name="Is Hosting?", value=f"Yes {probe['vpn-domain']}", inline=True)
            elif not probe['is-hosting']:
                embed.add_field(name="Is Hosting?", value=f"No", inline=True)
            if len(one) < 3:
                one = None
            embed.add_field(name="Nmap Results", value=f"```py\n{one}\n```", inline=False)
            embed.add_field(name="Ping Results", value=f"```\n{ping}\n```", inline=True)
            await message.edit(embed=embed, content="")
        except ValueError:
            embed = Embed(title="We ran into an error", description="That isn't a valid IP",
                          color=Color.from_hex("ff0000"))
            embed.set_footer(text=f"Caused by {ctx.author.display_name}", icon_url=ctx.author.avatar_url)
            await ctx.send(embed=embed)

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
        await ctx.send("Message sent. Thanks.\nRemember abuse of this feature will get you blacklisted from it",
                       ephemeral=True)
        if ctx.guild:
            full_message = f"{ctx.author.user} in {ctx.guild.name} #{ctx.channel.name} sent\n\n{message}"
        else:
            full_message = f"{ctx.author.user} DM sent\n\n{message}"
        paste = Paste(content=full_message)
        paste.save("https://paste.trent-buckley.com")
        await self.bot.owner.send(f"{paste.url}.md")

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
