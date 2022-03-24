from dis_snek.models import (
    Scale
)
import dis_snek
from dis_snek.api.voice.audio import YTDLAudio


class Voice(Scale):

    @dis_snek.slash_command("play", "play a song!")
    @dis_snek.slash_option("song", "The song to play", 3, True)
    async def play(self, ctx: dis_snek.InteractionContext, song: str):
        if not ctx.voice_state:
            # if we haven't already joined a voice channel
            # join the authors vc
            await ctx.author.voice.channel.connect()

        # Get the audio using YTDL
        audio = await YTDLAudio.from_url(song)
        await ctx.send(f"Now Playing: **{audio.entry['title']}**")
        # Play the audio
        await ctx.voice_state.play(audio)


def setup(bot):
    Voice(bot)
