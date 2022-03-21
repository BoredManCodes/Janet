import time
import random
from tkinter import Image
from urllib.parse import parse_qsl
from PIL import Image
import dis_snek
import requests
from dis_snek import listen, Embed, Webhook, Color, File
from dis_snek.client.errors import CommandCheckFailure
from dis_snek.client.utils import misc_utils
from dis_snek.ext.debug_scale import log
from dis_snek.models import (
    Scale,
    message_command,
    MessageContext,
    check,
    Context,
)
from dis_snek.models.discord import color
import dis_snek.api.events as events
from requests import PreparedRequest

from scales.admin import is_owner
import requests as req

class EventListener(Scale):
    # @listen()
    # async def on_command_error(self, event):
    #     embed = Embed(title=f"**Error in command: {event.command}**", description=f"```\n{event.error}\n```")
    #     await event.send(embed=embed)
    #     raise error

    @listen()
    async def on_member_update(self, event: events.MemberUpdate):
        if event.guild_id == 891613945356492890 and event.before.display_name != event.after.display_name and event.before.display_name is not None:
            embed = Embed(title=f"Name Change Detected:")
            embed.add_field(name='Before', value=event.before.display_name)
            embed.add_field(name='After', value=event.after.display_name)
            embed.set_footer(f"ID: {event.after.id}")
            embed.set_thumbnail(url=event.after.avatar.url)
            channel = await event.bot.get_channel(940919818561912872)
            await channel.send(embed=embed)

    @listen()
    async def om_member_add(self, event: events.MemberAdd):
        print("Member joined")
        if event.guild_id == 891613945356492890:
            print("beep")

            # Only detect if the user joined the Prism guild
            print(event.guild_id)
            if event.member.bot:  # Bloody bots
                return
            else:
                mod_log = await self.bot.get_channel(940919818561912872)
                if time.time() - event.member.created_at.timestamp() < 2592000:
                    # Send a message to the mods
                    title = f"{event.member.display_name} is potentially suspicious"
                    embed = Embed(title=title, color=color.FlatUIColors.CARROT)
                    embed.set_footer(text=f"Discord name: {event.member.display_name}\nDiscord ID: {event.member.id}",
                                     icon_url=event.member.avatar.url)
                    date_format = "%a, %d %b %Y %I:%M %p"
                    embed.set_thumbnail(
                        url="https://upload.wikimedia.org/wikipedia/commons/thumb/1/17/Warning.svg/1200px-Warning.svg.png")
                    embed.add_field(name="Joined Discord", value=event.member.created_at.strftime(date_format), inline=False)
                    await mod_log.send(embed=embed)
                else:
                    # Send a message to the mods
                    title = f"{event.member.display_name} joined the server"
                    embed = Embed(title=title, color=color.FlatUIColors.EMERLAND)
                    embed.set_footer(text=f"Discord name: {event.member.display_name}\nDiscord ID: {event.member.id}",
                                     icon_url=event.member.avatar_url)
                    date_format = "%a, %d %b %Y %I:%M %p"
                    embed.add_field(name="Joined Discord", value=event.member.created_at.strftime(date_format), inline=False)
                    await mod_log.send(embed=embed)
                # Send the welcome banner
                channel = await self.bot.get_channel(891613945356492893)
                messages = [
                    f"Welcome {event.member.display_name}\nIf you need anything from staff or simply have questions, ping a <@&858547638719086613>",
                    f"Hi {event.member.display_name}!\nIf you need anything from staff or simply have questions, ping a <@&858547638719086613>",
                    f"{event.member.display_name} joined us\nIf you need anything from staff or simply have questions, ping a <@&858547638719086613>",
                    f"{event.member.display_name} is *one of us*\nIf you need anything from staff or simply have questions, ping a <@&858547638719086613>",
                    f"Hoi {event.member.display_name}\nIf you need anything from staff or simply have questions, ping a <@&858547638719086613>",
                    f"{event.member.display_name} is here!\nIf you need anything from staff or simply have questions, ping a <@&858547638719086613>",
                    f"Welcome to the party {event.member.display_name}\nIf you need anything from staff or simply have questions, ping a <@&858547638719086613>",
                    f"Hey `@everyone` {event.member.display_name} joined Prism\nIf you need anything from staff or simply have questions, ping a <@&858547638719086613>"
                ]
                await channel.send(random.choice(messages))
                # req = PreparedRequest()
                # users = await bot.http.request(discord.http.Route("GET", f"/users/{event.id}"))
                # banner_id = users["banner"]
                # If statement because the user may not have a banner
                banner_id = "None"
                member_count = len([m for m in event.guild.members if not m.bot])
                # if not str(banner_id) == "None":
                #     banner_url = f"https://cdn.discordapp.com/banners/{event.member.id}/{event}?size=1024"
                #     req.prepare_url(
                #         url='https://api.xzusfin.repl.co/card?',
                #         params={
                #             'avatar': str(event.member.avatar.url.as(format='png')),
                #             'middle': f"{event.member.display_name} joined Prism",
                #             'name': "We now have",
                #             'bottom': f'{member_count} members',
                #             'text': color.Color.from_hex("#000000"),
                #             'avatarborder': color.Color.from_hex("#000000"),
                #             'avatarbackground': color.Color.from_hex("#000000"),
                #             'background': banner_url
                #         }
                #     )
                #     body = dict(parse_qsl(req.body))
                #     if 'code' in body:
                #         print("Not sending a banner due to invalid response")
                #         print(body)
                #         print(req.url)
                #     else:
                #         img_data = requests.get(req.url).content
                #         with open('Banner.png', 'wb') as handler:
                #             handler.write(img_data)
                #         try:
                #             Image.open('Banner.png')
                #             await channel.send(file=File('Banner.png'))
                #         except IOError:
                #             logger.error("Banner was not a valid image")
                # else:
                req = PreparedRequest()
                req.prepare_url(
                    url='https://api.xzusfin.repl.co/card?',
                    params={
                        'avatar': str(event.member.avatar.url_as(format='png')),
                        'middle': f"{event.member.display_name} joined Prism",
                        'name': "We now have",
                        'bottom': f'{member_count} members',
                        'text': color.Color.from_hex("#000000"),
                        'avatarborder': color.Color.from_hex("#000000"),
                        'avatarbackground': color.Color.from_hex("#000000"),
                        'background': "https://cdnb.artstation.com/p/assets/images/images/013/535/601/large/supawit-oat-fin1.jpg"
                    }
                )
                body = dict(parse_qsl(req.body))
                if 'code' in body:
                    print("Not sending a banner due to invalid response")
                    print(body)
                    print(req.url)
                else:
                    img_data = requests.get(req.url).content
                    with open('Banner.png', 'wb') as handler:
                        handler.write(img_data)
                    try:
                        Image.open('Banner.png')
                        await channel.send(file=File('Banner.png'))
                    except IOError:
                        log.error("Banner was not a valid image")
            # Give the user the New Member role
            role = await misc_utils.get(event.guild.roles, name="New Member")
            await event.member.add_role(role=role, reason="New member joined")

    @listen()
    async def on_member_remove(self, event: events.MemberRemove):
        if event.member.bot:
            return
        else:
            messages = [
                f"Goodbye {event.member.display_name}",
                f"It appears {event.member.display_name} has left",
                f"{event.member.display_name} has disappeared :(",
                f"We wish {event.member.display_name} well in their travels",
                f"Toodles {event.member.display_name}!",
                f"{event.member.display_name} found love elsewhere :(",
                f"{event.member.display_name} left\nSee you later alligator",
                f"{event.member.display_name} left\nBye Felicia",
                f"{event.member.display_name} left\nSo long, and thanks for all the fish!",
                f"{event.member.display_name} left\nGoodbye, Vietnam! That’s right, I’m history, I’m outta here, "
            ]
            general = await self.bot.get_channel(891613945356492893)
            await general.send(random.choice(messages))
            channel = await self.bot.get_channel(940919818561912872)
            title = f"{event.member.display_name} left the server"
            embed = Embed(title=title, color=color.BrandColours.RED)
            embed.set_footer(text=f"Discord name: {event.member.display_name}\nDiscord ID: {event.member.id}",
                             icon_url=event.member.avatar.url)
            date_format = "%a, %d %b %Y %I:%M %p"
            embed.set_author(name=str(event), icon_url=event.member.avatar.url)
            embed.set_thumbnail(url=event.member.avatar.url)
            embed.add_field(name="Joined Server", value=event.member.joined_at.strftime(date_format), inline=False)
            embed.add_field(name="Joined Discord", value=event.member.created_at.strftime(date_format), inline=False)
            embed.set_footer(text='ID: ' + str(event.member.id))
            await channel.send(embed=embed)

def setup(bot):
    EventListener(bot)
