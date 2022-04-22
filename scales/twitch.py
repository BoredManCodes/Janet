import concurrent.futures
import os
from asyncio import sleep

import aiohttp
import dis_snek
from attr import dataclass
from dis_snek import slash_command, InteractionContext, slash_option, OptionTypes
from dis_snek.models import (
    Scale
)
from twitchAPI import Twitch as TwitchAPI
from twitchAPI.types import TwitchAuthorizationException

from main import ConfigSectionMap, log


class Twitch(Scale):
    @slash_command("twitch_avatar", "Get a user's Twitch avatar")
    @slash_option("username", "The username to lookup", opt_type=OptionTypes.STRING, required=True)
    async def twitch_avatar(self, ctx: InteractionContext, username: str):
        '''Gives you the avatar that a specified Twitch.tv user has'''

        # Set up your headers - in an actual application you'd
        # want these to be in init or a config file
        headers = {
            'Authorization': '5c8ftpbbhbw6wmp03glcufpkrmqsng'  # This is a fake token
        }

        # URL is a constant each time, params will change every time the command is called
        url = 'https://api.twitch.tv/helix/users'
        params = {
            'login': username
        }

        # Send the request - aiohttp is a non-blocking form of requests
        # In an actual application, you may have a single ClientSession that you use through the
        # whole cog, or perhaps the whole bot
        # In this example I'm just making one every time the command is called
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as r:
                response = await r.json()  # Get a json response

        # Respond with their avatar
        avatar = response['data'][0]['profile_image_url']
        await ctx.send(avatar)

def setup(bot):
    Twitch(bot)
