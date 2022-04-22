import contextlib
import io
import sys
from base64 import urlsafe_b64encode
from uuid import uuid4 as uuid
import dis_snek
from dis_snek import Button, ButtonStyles, File, Embed
from dis_snek.models import (
    Scale,
    message_command,
    MessageContext,
    check,
    Context,
)

from scales.admin import is_owner
from scales.moderation import calcEpochSec


class MessageCommands(Scale):
    @message_command(name="userinfo")
    async def userinfo(self, ctx: MessageContext, user: dis_snek.Member):
        # if user.activities:  # check if the user has an activity
        #     if str(user.activities[0].type) == "ActivityType.playing":
        #         activity = "Playing:"
        #     elif str(user.activities[0].type) == "ActivityType.streaming":
        #         activity = "Streaming:"
        #     elif str(user.activities[0].type) == "ActivityType.listening":
        #         activity = "Listening to:"
        #     elif str(user.activities[0].type) == "ActivityType.watching":
        #         activity = "Watching"
        #     elif str(user.activities[0].type) == "ActivityType.custom":
        #         activity = ""
        #     elif str(user.activities[0].type) == "ActivityType.competing":
        #         activity = "Competing in:"
        #     else:
        #         activity = "Funkiness"
        #     has_activity = True
        # else:  # if they don't we can't reference it
        #     has_activity = False
        # if user.status.name == "online":
        #     statusemoji = "\N{LARGE GREEN CIRCLE}"
        #     status = "Online"
        # elif user.status.name == "offline":
        #     statusemoji = "\N{MEDIUM WHITE CIRCLE}\N{VARIATION SELECTOR-16}"
        #     status = "Offline"
        # elif user.status.name == "dnd":
        #     statusemoji = "\N{LARGE RED CIRCLE}"
        #     status = "Do not disturb"
        # elif user.status.name == "idle":
        #     statusemoji = "\N{LARGE ORANGE CIRCLE}"
        #     status = "Idling"
        # else:  # just in case some funky shit is going on
        #     statusemoji = "\N{LARGE PURPLE CIRCLE}"
        #     status = ""
        try:
            top_role = user.roles[-1]  # first element in roles is `@everyone` and last is top role
            embed = Embed(color=top_role.color, description=user.mention)
        except Exception as e:
            embed = Embed(description=user.mention)
            print(e)
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.set_thumbnail(url=user.display_avatar.url)
        # embed.add_field(name="Current Status", value=f"{statusemoji} | {status}", inline=False)
        # if has_activity:
        #     try:
        #         if str(user.activities[0].details) == "None":
        #             embed.add_field(name="Current Activity",
        #                             value=f"{activity} {user.activities[0].name}", inline=False)
        #         else:
        #             embed.add_field(name="Current Activity",
        #                             value=f"{activity} {user.activities[0].name} | {user.activities[0].details}",
        #                             inline=False)
        #     except:
        #         embed.add_field(name="Current Activity",
        #                         value=f"{activity} {user.activities[0].name}", inline=False)
        dt = user.joined_at
        joined = calcEpochSec(dt)
        joined_time = str(joined).split('.')
        dt = user.created_at
        created = calcEpochSec(dt)
        discord_joined_time = str(created).split('.')
        embed.add_field(name="Discord Name", value=f"{user.user.username}#{user.discriminator}")
        embed.add_field(name="Joined Server", value=f"<t:{joined_time[0]}:R>", inline=False)
        members = sorted(ctx.guild.members, key=lambda m: m.joined_at)
        embed.add_field(name="Join Position", value=str(members.index(user) + 1), inline=False)
        embed.add_field(name="Joined Discord", value=f"<t:{discord_joined_time[0]}:R>", inline=False)
        if len(user.roles) > 1:
            res = user.roles[::-1]
            role_string = ' '.join([r.mention for r in res][:-1])
            embed.add_field(name="Roles [{}]".format(len(user.roles) - 1), value=role_string, inline=False)
        embed.set_footer(text=f"ID: {user.id}")
        await ctx.send(embed=embed)

    @message_command()
    @check(is_owner())
    async def owner_only(self, ctx: MessageContext):
        await ctx.send("You are the owner")

    @message_command()
    async def test_button(self, ctx: MessageContext):
        print("test button")
        await ctx.send("Danger Noodle!", components=Button(ButtonStyles.DANGER, "boop", custom_id="boop"))

    @message_command()
    async def transcript(self, ctx):
        css = '''
            body {
            background-color: #36393e;
            color: #dcddde;
            }
            a {
                color: #0096cf;
            }
            .info {
                display: flex;
                max-width: 100%;
                margin: 0 5px 10px;
            }
            .guild-icon-container {
                flex: 0;
            }
            .guild-icon {
                max-width: 88px;
                max-height: 88px;
            }
            .metadata {
                flex: 1;
                margin-left: 10px;
            }
            .guild-name {
                font-size: 1.4em;
            }
            .channel-name {
                font-size: 1.2em;
            }
            .channel-topic {
                margin-top: 2px;
            }
            .channel-message-count {
                margin-top: 2px;
            }
            .chatlog {
                max-width: 100%;
                margin-bottom: 24px;
            }
            .message-group {
                display: flex;
                margin: 0 10px;
                padding: 15px 0;
                border-top: 1px solid;
            }
            .author-avatar-container {
                flex: 0;
                width: 40px;
                height: 40px;
            }
            .author-avatar {
                border-radius: 50%;
                height: 40px;
                width: 40px;
            }
            .messages {
                flex: 1;
                min-width: 50%;
                margin-left: 20px;
            }
            .author-name {
                font-size: 1em;
                font-weight: 500;
            }
            .timestamp {
                margin-left: 5px;
                font-size: 0.75em;
            }
            .message {
                padding: 2px 5px;
                margin-right: -5px;
                margin-left: -5px;
                background-color: transparent;
                transition: background-color 1s ease;
            }
            .content {
                font-size: 0.9375em;
                word-wrap: break-word;
            }
            .mention {
                color: #7289da;
            }
        '''

        async def check_message_mention(msgs: dis_snek.Message):
            user_mentions = []
            if msgs.mention_users is not None:
                async for member in msgs.mention_users:
                    user_mentions.append(member)
            role_mentions = []
            if msgs.mention_roles:
                async for role in msgs.mention_roles:
                    role_mentions.append(role)
            channel_mentions = []
            if msgs.mention_channels:
                for channel in msgs.mention_channels:
                    channel_mentions.append(channel)
            user_mentions: list = user_mentions
            role_mentions: list = role_mentions
            channel_mentions: list = channel_mentions
            total_mentions = user_mentions + role_mentions + channel_mentions
            m: str = msgs.content
            for mentions in total_mentions:
                if mentions in user_mentions:
                    for mention in user_mentions:
                        m = m.replace(str(f"<@{mention.id}>"),
                                      f"<span class=\"mention\">@{mention.display_name}</span>")
                        m = m.replace(str(f"<@!{mention.id}>"),
                                      f"<span class=\"mention\">@{mention.display_name}</span>")
                elif mentions in role_mentions:
                    for mention in role_mentions:
                        m = m.replace(str(f"<@&{mention.id}>"),
                                      f"<span class=\"mention\">@{mention.name}</span>")
                elif mentions in channel_mentions:
                    for mention in channel_mentions:
                        m = m.replace(str(f"<#{mention.id}>"),
                                      f"<span class=\"mention\">#{mention.name}</span>")
                else:
                    pass
            return m

        messages = await ctx.channel.history(limit=None).flatten()

        f = f'''
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset=utf-8>
                <meta name=viewport content="width=device-width">
                <style>
                    {css}
                </style>
            </head>
            <body>
                <div class=info>
                    <div class=guild-icon-container><img class=guild-icon src={str(ctx.guild.icon.url).replace('.png.png', '.png')}></div>
                    <div class=metadata>
                        <div class=guild-name>{ctx.guild.name}</div>
                        <div class=channel-name>{ctx.channel.name}</div>
                        <div class=channel-message-count>{len(messages)} messages</div>
                    </div>
                </div>
            '''

        for message in messages[::-1]:
            if message.embeds:
                content = 'Embed'

            elif message.attachments:
                # IS AN IMAGE:
                if message.attachments[0].url.endswith(('jpg', 'png', 'gif', 'bmp')):
                    if message.content:
                        content = check_message_mention(
                            message) + '<br>' + f"<img src=\"{message.attachments[0].url}\" width=\"200\" alt=\"Attachment\" \\>"
                    else:
                        content = f"<img src=\"{message.attachments[0].url}\" width=\"200\" alt=\"Attachment\" \\>"

                # IS A VIDEO
                elif message.attachments[0].url.endswith(('mp4', 'ogg', 'flv', 'mov', 'avi')):
                    if message.content:
                        content = check_message_mention(message) + '<br>' + f'''
                        <video width="320" height="240" controls>
                          <source src="{message.attachments[0].url}" type="video/{message.attachments[0].url[-3:]}">
                        Your browser does not support the video.
                        </video>
                        '''
                    else:
                        content = f'''
                        <video width="320" height="240" controls>
                          <source src="{message.attachments[0].url}" type="video/{message.attachments[0].url[-3:]}">
                        Your browser does not support the video.
                        </video>
                        '''
                elif message.attachments[0].url.endswith(('mp3', 'boh')):
                    if message.content:
                        content = check_message_mention(message) + '<br>' + f'''
                        <audio controls>
                          <source src="{message.attachments[0].url}" type="audio/{message.attachments[0].url[-3:]}">
                        Your browser does not support the audio element.
                        </audio>
                        '''
                    else:
                        content = f'''
                        <audio controls>
                          <source src="{message.attachments[0].url}" type="audio/{message.attachments[0].url[-3:]}">
                        Your browser does not support the audio element.
                        </audio>
                        '''
                # OTHER TYPE OF FILES
                else:
                    # add things
                    pass
            else:
                content = await check_message_mention(message)

            f += f'''
            <div class="message-group">
                <div class="author-avatar-container"><img class=author-avatar src={message.author.avatar.url}></div>
                <div class="messages">
                    <span class="author-name" >{message.author.display_name}</span><span class="timestamp">{message.created_at.strftime("%b %d, %Y %H:%M")}</span>
                    <div class="message">
                        <div class="content"><span class="markdown">{content}</span></div>
                    </div>
                </div>
            </div>
            '''
        f += '''
                </div>
            </body>
        </html>
        '''

        with open(f"transcripts/{urlsafe_b64encode(uuid().bytes)[0:22]}.html", mode='w', encoding='utf-8') as file:
            print(io.StringIO(f).read(), file=file)
            await ctx.reply(f"Transcript: https://transcripts.boredman.net/{urlsafe_b64encode(uuid().bytes)[0:22]}")


def setup(bot):
    MessageCommands(bot)
