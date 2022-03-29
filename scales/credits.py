from dis_snek import Embed, slash_command, InteractionContext
from dis_snek.models import (
    Scale
)
from dis_snek.models.discord import color


class Credits(Scale):
    # My way of paying homage and saying thanks to those that have helped me on my journey to making Janet the bot it is
    @slash_command(name="credits", description="My way of saying thanks")
    async def credits(self, ctx: InteractionContext):
        credits_text = "[LordOfPolls](https://github.com/LordOfPolls) - Author of [Inquiry](https://github.com/LordOfPolls/Inquiry)," \
                  " the bot Janet ~~stole~~ borrowed it's codebase from and [Dis-Secretary](https://github.com/Discord-Snake-Pit/Dis-Secretary), " \
                  "where the GitHub handling code came from\n\n" \
                    \
                  "[zevaryx](https://github.com/zevaryx) - Janet's error handling code was taken from zev's bot " \
                  "[JARVIS](https://git.zevaryx.com/stark-industries/jarvis/), Janet also uses [PastyPY](https://github.com/zevaryx/pastypy/)" \
                  " which is another project of zev's to allow asynchronous saving of pastes to pasty sites\n\n" \
                    \
                  "[Wolfhound905](https://github.com/Wolfhound905) - Informing me of `fetch_message` instead of `get_message` and solved a problem I've been having for weeks\n\n" \
                    \
                  "[The entire dis-snek guild](https://discord.gg/dis-snek) - Helping me when I do stupid stuff or run into a wall and get stuck arguing with my code\n\n"
        embed = Embed(title="Credits and Thanks",
                      description=credits_text,
                      color=color.MaterialColors.DEEP_PURPLE
                      )
        embed.set_image("https://cdn.discordapp.com/attachments/943106707381444678/958331932209479741/thumbs-up-float.gif")
        await ctx.send(embeds=embed)

def setup(bot):
    Credits(bot)
