import contextlib
import io
from dis_snek import listen, Embed
from dis_snek.models import (
    Scale,
    check
)
from dis_snek.models.discord import color

from scales.admin import is_owner


class MessageEvents(Scale):
    @listen()
    async def on_message_create(self, event):
        if ".com/channels" in event.message.content:
            if event.message.guild and event.message.author != event.bot.user:  # Check we aren't in DM's to avoid looping
                await event.message.delete()
                link = event.message.content.split('/')
                server_id = int(link[4])
                channel_id = int(link[5])
                msg_id = int(link[6])
                server = await event.bot.get_guild(server_id)
                channel = server.get_channel(channel_id)
                quoted = await channel.get_message(msg_id)
                embed = Embed(description=f"**{quoted.content}**\n\nSent: {quoted.created_at}", color=color.Color.from_hex("00ff00"))
                embed.set_author(name=f"{quoted.author.display_name} in #{quoted.channel.name}",
                                 icon_url=quoted.author.avatar._url,
                                 url=quoted.jump_url)
                embed.set_footer(text=f"Quoted by {event.message.author.display_name}", icon_url=event.message.author.avatar._url)
                if event.message.author != quoted.author:  # Don't DM user they quoted themselves
                    await quoted.author.send(f"{event.message.author.display_name} mentioned your message ```{quoted.content}``` in {event.message.channel.mention}!")
                await event.message.channel.send(embed=embed)
        # log = event.bot.get_channel(940919818561912872)
        # blacklist_channels = [907718985343197194, 891614699374915584,
        #                       891614663253585960]  # Don't listen to the message logger channel to avoid looping
        # if len(event.message.content) > 1500 and not event.message.channel.id in blacklist_channels:
        #     step = 1000
        #     for i in range(0, len(event.message.content), 1000):
        #         split = event.message.content[i:step]
        #         step += 1000
        #         await log.send(f"<#{event.message.channel.id}> {event.message.author.display_name} ({event.message.author.id}) sent: {split}")
        #
        # if event.message.channel.id in blacklist_channels:
        #     return
        # else:  # Otherwise, do the logging thing
        #     await log.send(f"<#{event.message.channel.id}> {event.message.author.display_name} ({event.message.author.id}) sent: {event.message.content}")

        if event.message.author == event.bot.user:  # Don't listen to yourself
            return
        if "https://discord.gift/" in event.message.content.lower():  # Some dumbass sent free nitro
            await event.message.channel.send(":warning: FREE NITRO! :warning:\nThis link appears to be legitimate :D")
            return
        # if not event.message.guild and event.message.author != event.bot.user:  # If message not in a guild it must be a DM
        #     message_filtered = str(event.message.content).replace('www', '').replace('http', '')  # No links pls
        #     url = 'https://neutrinoapi.net/bad-word-filter'  # Filter out bad boy words
        #     params = {
        #         'user-id': config("NaughtyBoy_user"),
        #         'api-key': config("NaughtyBoy_key"),
        #         'content': message_filtered,
        #         'censor-character': '•',
        #         'catalog': 'strict'
        #     }
        #     postdata = parse.urlencode(params).encode()
        #     req = request.Request(url, data=postdata)
        #     response = request.urlopen(req)
        #     result = json.loads(response.read().decode("utf-8"))
        #     async with aiohttp.ClientSession() as session:
        #         webhook = Webhook.from_url(config("MOD"), adapter=AsyncWebhookAdapter(session))
        #         await webhook.send(
        #             f"{result['censored-content']}",
        #             username=f"{message.author.display_name} in DM", avatar_url=message.author.avatar_url)
        if str(event.bot.user.id) in event.message.content:
            reactions = ["❓"]
            for reaction in reactions:
                await event.message.add_reaction(reaction)


def setup(bot):
    MessageEvents(bot)
