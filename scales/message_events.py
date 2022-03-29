import contextlib
import io
import uuid

import dis_snek
from dis_snek import listen, Embed, ActionRow, Button, ButtonStyles
from dis_snek.api.events import MessageCreate
from dis_snek.models import (
    Scale,
    check
)
from dis_snek.models.discord import color
from pytube import YouTube
from scales.admin import is_owner


class MessageEvents(Scale):
    @listen(MessageCreate)
    async def on_message_create(self, event: MessageCreate):
        # Fix YouTube embeds for mobile users
        if "https://www.youtube.com/watch?v=" in event.message.content:
            try:
                word_array = event.message.content.split(" ")
                for word in word_array:
                    if "https://www.youtube.com/watch?v=" in word:
                        print("Detected youtube video. attempting download")
                        await event.message.suppress_embeds()
                        await event.message.add_reaction("<:youtube:957437121545793616>")
                        yt = YouTube(word)
                        embed = Embed(title=yt.title, description=yt.description[:250], url=yt.watch_url)
                        embed.add_field("Author", yt.author, inline=True)
                        embed.add_field("Views", yt.views, inline=True)
                        embed.add_field("Uploaded", yt.publish_date, inline=False)
                        embed.add_field("Age restricted?", yt.age_restricted, inline=True)
                        embed.set_thumbnail(yt.thumbnail_url)

                        components: list[ActionRow] = [
                            ActionRow(
                                Button(
                                    style=ButtonStyles.BLURPLE,
                                    label="⏯",
                                )
                            )
                        ]
                        filename = f"{str(uuid.uuid4())}.mp4"
                        message = await event.message.channel.send(embeds=embed, components=components)
                        video = yt.streams.filter(progressive=True, file_extension='mp4').order_by(
                            'resolution').asc().first().download(output_path="/home/user/ShareX-Upload-Server/src/server/uploads", filename=filename)
                        # print(video)
                        try:
                            # you need to pass the component you want to listen for here
                            # you can also pass an ActionRow, or a list of ActionRows. Then a press on any component in there will be listened for
                            used_component = await self.bot.wait_for_component(components=components,
                                                                               timeout=30)
                        except TimeoutError:
                            components[0].components[0].disabled = True
                            await message.edit(components=components)
                        else:
                            components[0].components[0].disabled = True
                            await message.edit(components=components)
                            content = f"https://share.boredman.net/{filename}"
                            await used_component.context.send(content, ephemeral=False)

            except BaseException as e:
                print(e)
                pass
        if event.message.guild:
            if event.message.channel.id != 907718985343197194:  # don't do shit if the messages were in the logs channel
                if ".com/channels" in event.message.content:
                    if event.message.guild and event.message.author != event.bot.user:  # Check we aren't in DM's to avoid looping
                        await event.message.delete()
                        link = event.message.content.split('/')
                        server_id = int(link[4])
                        channel_id = int(link[5])
                        msg_id = int(link[6])
                        server = event.bot.get_guild(server_id)
                        channel = server.get_channel(channel_id)
                        quoted = await channel.fetch_message(msg_id)
                        if event.message.guild != quoted.guild:
                            quoted_author = await self.bot.fetch_member(quoted.author.id, quoted.guild.id)
                        else:
                            quoted_author = await self.bot.fetch_member(quoted.author.id, event.message.guild.id)
                        if quoted.attachments:
                            embed = Embed(description=f"{quoted.content}\n\nSent: {quoted.created_at}")
                            embed.set_image(quoted.attachments[0].url)
                        elif quoted.embeds:
                            if quoted.embeds[0].title is not None and quoted.embeds[0].description is not None:
                                embed = Embed(description=f"Embed title: {quoted.embeds[0].title}\n\n{quoted.embeds[0].description}")
                            elif quoted.embeds[0].title is None and quoted.embeds[0].description is not None:
                                embed = Embed(description=f"{quoted.embeds[0].description}")
                            elif quoted.embeds[0].title is not None and quoted.embeds[0].description is None:
                                embed = Embed(description=f"Embed title: {quoted.embeds[0].title}")
                            elif quoted.embeds[0].title and quoted.embeds[0].description is None:
                                return
                        else:
                            embed = Embed(description=f"**{quoted.content}**\n\nSent: {quoted.created_at}")
                        embed.color = color.MaterialColors.DEEP_PURPLE
                        if "#0000" in str(quoted.author): # user is a webhook and will throw a bunch of errors
                            embed.set_author(name=f"Webhook in #{quoted.channel.name}",
                                             url=quoted.jump_url)
                        else:
                            embed.set_author(name=f"{quoted_author.display_name} in #{quoted.channel.name}",
                                             icon_url=quoted_author.display_avatar.url,
                                             url=quoted.jump_url)
                        embed.set_footer(text=f"Quoted by {event.message.author.display_name}", icon_url=event.message.author.avatar._url)
                        await event.message.channel.send(embed=embed)

                        try:
                            if not quoted.author.bot:
                                if event.message.author != quoted.author: # Don't DM user they quoted themselves
                                    try:
                                        if "VIEW_CHANNEL" in str(event.message.channel.permissions_for(quoted_author)):
                                            await quoted.author.send(f"{event.message.author.display_name} mentioned your message\n```\n{quoted.content}```\nin {event.message.channel.mention}!")
                                    except RuntimeError:
                                        return
                        except dis_snek.errors.Forbidden:
                            return
                if event.message.author == event.bot.user:  # Don't listen to yourself
                    return
                if "https://discord.gift/" in event.message.content.lower():  # Some dumbass sent free nitro
                    await event.message.channel.send(":warning: FREE NITRO! :warning:\nThis link appears to be legitimate :D")
                    return
                if str(event.bot.user.id) in event.message.content:
                    reactions = ["❓"]
                    for reaction in reactions:
                        await event.message.add_reaction(reaction)


def setup(bot):
    MessageEvents(bot)
