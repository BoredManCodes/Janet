import json
from datetime import datetime

from dis_snek import context_menu, CommandTypes, InteractionContext, Embed
from dis_snek.models import (
    Scale
)


class Contexts(Scale):
    @context_menu(name="User Info", context_type=CommandTypes.USER)
    async def user_context_menu(self, ctx: InteractionContext):
        user = await self.bot.get_user(ctx.target_id)
        if user.activities:  # check if the user has an activity
            if str(user.activities[0].type) == "ActivityType.playing":
                activity = "Playing:"
            elif str(user.activities[0].type) == "ActivityType.streaming":
                activity = "Streaming:"
            elif str(user.activities[0].type) == "ActivityType.listening":
                activity = "Listening to:"
            elif str(user.activities[0].type) == "ActivityType.watching":
                activity = "Watching"
            elif str(user.activities[0].type) == "ActivityType.custom":
                activity = ""
            elif str(user.activities[0].type) == "ActivityType.competing":
                activity = "Competing in:"
            else:
                activity = "Funkiness"
            has_activity = True
        else:  # if they don't we can't reference it
            has_activity = False
        if user.status.name == "online":
            statusemoji = "\N{LARGE GREEN CIRCLE}"
            status = "Online"
        elif user.status.name == "offline":
            statusemoji = "\N{MEDIUM WHITE CIRCLE}\N{VARIATION SELECTOR-16}"
            status = "Offline"
        elif user.status.name == "dnd":
            statusemoji = "\N{LARGE RED CIRCLE}"
            status = "Do not disturb"
        elif user.status.name == "idle":
            statusemoji = "\N{LARGE ORANGE CIRCLE}"
            status = "Idling"
        else:  # just in case some funky shit is going on
            statusemoji = "\N{LARGE PURPLE CIRCLE}"
            status = ""
        top_role = user.roles[-1]  # first element in roles is `@everyone` and last is top role
        embed = Embed(color=top_role.color, description=user.mention)
        embed.set_author(name=str(user), icon_url=user.avatar_url)
        embed.set_thumbnail(url=user.avatar_url)
        embed.add_field(name="Current Status", value=f"{statusemoji} | {status}", inline=False)
        if has_activity:
            try:
                if str(user.activities[0].details) == "None":
                    embed.add_field(name="Current Activity",
                                    value=f"{activity} {user.activities[0].name}", inline=False)
                else:
                    embed.add_field(name="Current Activity",
                                    value=f"{activity} {user.activities[0].name} | {user.activities[0].details}",
                                    inline=False)
            except:
                embed.add_field(name="Current Activity",
                                value=f"{activity} {user.activities[0].name}", inline=False)
        joined_time = str((user.joined_at - datetime(1970, 1, 1)).total_seconds()).split('.')
        discord_joined_time = str((user.created_at - datetime(1970, 1, 1)).total_seconds()).split('.')
        embed.add_field(name="Discord Name", value=f"{user.name}#{user.discriminator}")
        embed.add_field(name="Joined Server", value=f"<t:{joined_time[0]}:R>", inline=False)
        members = sorted(ctx.guild.members, key=lambda m: m.joined_at)
        embed.add_field(name="Join Position", value=str(members.index(user) + 1), inline=False)
        embed.add_field(name="Joined Discord", value=f"<t:{discord_joined_time[0]}:R>", inline=False)
        if len(user.roles) > 1:
            res = user.roles[::-1]
            role_string = ' '.join([r.mention for r in res][:-1])
            embed.add_field(name="Roles [{}]".format(len(user.roles) - 1), value=role_string, inline=False)
        embed.set_footer(text='ID: ' + str(user.id))
        await ctx.send(embed=embed)
        # # Game stuffs
        # IP = config("GAME_IP")
        # url = f"http://{IP}/players/{user.display_name}/stats"
        # # print(f"http://{IP}/players/{user.display_name}/stats")
        # page = requests.get(url)
        # stats = json.loads(page.text)
        # try:
        #     if stats['error']:
        #         return
        # except:
        #     # Game time
        #     sec = int(stats["time"])
        #     sec_value = sec % (24 * 3600)
        #     hour_value = sec_value // 3600
        #     sec_value %= 3600
        #     min_value = sec_value // 60
        #     sec_value %= 60
        #     if hour_value != 0:
        #         game_time = f"{hour_value} hours, {min_value} minutes"
        #     else:
        #         game_time = f"{min_value} minutes"
        #     # Death time
        #     sec = int(stats["death"])
        #     sec_value = sec % (24 * 3600)
        #     hour_value = sec_value // 3600
        #     sec_value %= 3600
        #     min_value = sec_value // 60
        #     sec_value %= 60
        #     if hour_value != 0:
        #         death_time = f"{hour_value} hours, {min_value} minutes"
        #     else:
        #         death_time = f"{min_value} minutes"
        #     embed = Embed(color=top_role.color,
        #                   title=f"{user.display_name}'s current game stats")
        #     embed.add_field(name="Time spent in game:", value=game_time, inline=True)
        #     embed.add_field(name="Time since last death:", value=death_time, inline=True)
        #     embed.add_field(name="Kills:", value=stats["kills"], inline=True)
        #     embed.add_field(name="Deaths:", value=stats["deaths"], inline=True)
        #     embed.add_field(name="XP level:", value=stats["level"], inline=True)
        #     embed.add_field(name="Health:", value=stats["health"], inline=True)
        #     embed.add_field(name="Hunger:", value=stats["food"], inline=True)
        #     embed.add_field(name="Times jumped:", value=stats["jumps"], inline=True)
        #     embed.add_field(name="World:", value=stats["world"], inline=True)
        #     embed.set_thumbnail(url=f"https://heads.discordsrv.com/head.png?name={user.display_name}&overlay")
        #     await ctx.send(embed=embed, ephemeral=True)

def setup(bot):
    Contexts(bot)
