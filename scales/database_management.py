import os
import sys

from dis_snek.models import (
    Scale
)

# from main import log


class DatabaseManagement(Scale):
    async def make_settings(self):
        for guild in self.bot.guilds:
            path = "settings/" + str(guild.id)
            try:
                os.makedirs(path)
                print("Making directory: " + path)
                if "linux" or "darwin" in sys.platform:
                    os.system(f"cp settings_sample.json {path}/settings.json")
                elif "win" in sys.platform:
                    os.system(f"copy settings_sample.json {path}/settings.json")
                else:
                    print("I have no idea what OS this is, trying random things to copy settings")
                    os.system(f"cp settings_sample.json {path}/settings.json")
                    os.system(f"copy settings_sample.json {path}/settings.json")

            except FileExistsError:
                print("Guild settings already exist " + path)


def setup(bot):
    DatabaseManagement(bot)
