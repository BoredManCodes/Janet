import io
import ipaddress
import json
import os
import subprocess
import aiohttp
import dis_snek
from dis_snek import Embed, Color, slash_command, InteractionContext
from dis_snek.models import Scale
from dis_snek.models.snek.application_commands import SlashCommandOption, OptionTypes
from pastypy import Paste


class ApplicationCommands(Scale):
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
        params = {
            'user-id': "BoredManSwears",
            'api-key': "ghwsjEpDP31gv0tzrz732ShPNBVIf2KZ9bFGkJkw4IERSsxA",
            'ip': address,
            'reverse-lookup': True
        }
        if address is None:
            embed = Embed(title="We ran into an error", description="You forgot to add an IP",
                          color=Color.from_hex("ff0000"))
            embed.set_footer(text=f"Caused by {ctx.author.display_name}", icon_url=ctx.author.avatar_url)
            await ctx.send(embed=embed)
            return

        try:
            # This will return an error if it's not a valid IP. Saves me doing input validation
            ipaddress.ip_address(address)
        except ValueError:
            embed = Embed(title="We ran into an error", description="That isn't a valid IP",
                          color=Color.from_hex("ff0000"))
            embed.set_footer(text=f"Caused by {ctx.author.display_name}", icon_url=ctx.author.avatar.url)
            await ctx.send(embed=embed)
        await ctx.defer(ephemeral=True)
        # os.system(f"ping -c 1  {address}")
        try:
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
            async with aiohttp.ClientSession() as session:
                async with session.get('https://neutrinoapi.net/ip-info', data=params) as req:
                    print(req.status)
                    req = await req.text()
            result = json.loads(req)
            # probe for info
            async with aiohttp.ClientSession() as session:
                async with session.get('https://neutrinoapi.net/ip-probe', data=params) as req:
                    print(req.status)
                    req = await req.text()
            probe = json.loads(req)
            embed = Embed(title="IP lookup", description=f"Lookup details for {address}",
                          color=Color.from_hex("ff0000"))
            embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.avatar.url)
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
            await ctx.send(embed=embed, content="")
        except Exception as e:
            paste = Paste(content=str(e))
            paste.save("https://paste.trent-buckley.com")
            embed = Embed(title="We encountered an error",
                          description=f"Something went wrong, for more info please see the [log]({paste.url}.md)",
                          color=Color.from_hex("ff0000"))
            embed.set_footer(text=f"Caused by {ctx.author.display_name}", icon_url=ctx.author.avatar.url)
            await ctx.send(embeds=embed)

    @slash_command(name="count-members",
                   description="Counts all members with a certain role",
                   options=[
                       SlashCommandOption(
                           name="role",
                           description="The role you want to count",
                           type=OptionTypes.ROLE,
                           required=True
                       )
                   ])
    async def count_members(self, ctx: InteractionContext, role: dis_snek.Role):
        try:
            count = len(role.members)
            if role.id == ctx.guild_id:
                count = ctx.guild.member_count
            if count == 1:
                title = f"**{count} member with the {role.mention} role**"
            else:
                title = f"**{count} members with the {role.mention} role**"
            embed = Embed(description=f"{title}", color=role.color)
            embed.set_footer(text=f"Issued by {ctx.author.display_name}", icon_url=ctx.author.avatar.url)
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(str(e))


def setup(bot):
    ApplicationCommands(bot)