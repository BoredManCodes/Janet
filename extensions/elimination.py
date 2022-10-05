import attrs
from naff import InteractionContext, context_menu, CommandTypes, MISSING, Embed, BrandColors

from extensions.shared import ExtensionBase
from models.poll import PollOption, PollData

THE_ALLIANCE = 853993464030298132
INQUIRY = 1013821165191581756
DEV_SERVER = 985991455074050078
TESTING_SCOPES = [THE_ALLIANCE, INQUIRY, DEV_SERVER]


class Elimination(ExtensionBase):
    async def eliminate(self, ctx: InteractionContext, poll: PollData, highest=True) -> None:
        await ctx.defer()
        async with poll.lock:
            new_options = poll.poll_options.copy()
            sorted_votes: list[PollOption] = sorted(poll.poll_options, key=lambda x: len(x.voters), reverse=highest)
            top_voted = sorted_votes[0]
            possible_ties = [o for o in sorted_votes if len(o.voters) == len(top_voted.voters)]

            for option in possible_ties:
                new_options.remove(option)

            if len(new_options) == 0:
                await ctx.send("No options left to eliminate")
                return

            new_poll = attrs.evolve(
                poll,
                closed=False,
                expired=False,
                expire_time=None,
                poll_options=new_options,
                message_id=MISSING,
                thread_message_id=MISSING,
            )
            new_poll.reallocate_emoji()
        if not poll.closed:
            await self.bot.close_poll(ctx.target_id)

        embed = Embed(
            "Elimination",
            description=f"Eliminated {', '.join(f'`{o.text}`' for o in possible_ties)} from `{poll.title}`",
            color=BrandColors.BLURPLE,
        )
        og_poll_message = await ctx.fetch_message(poll.message_id)
        embed.add_field("Original Poll", f"[Click Here]({og_poll_message.jump_url})")

        await ctx.send(embed=embed)
        await new_poll.send(ctx)
        await self.bot.poll_cache.store_poll(new_poll)

    @context_menu(name="Eliminate-Highest", context_type=CommandTypes.MESSAGE, scopes=TESTING_SCOPES)
    async def eliminate_highest(self, ctx: InteractionContext):
        if poll := await self.bot.poll_cache.get_poll(ctx.target_id):
            await self.eliminate(ctx, poll, highest=True)
        else:
            await ctx.send("This is not a poll.")

    @context_menu(name="Eliminate-Lowest", context_type=CommandTypes.MESSAGE, scopes=TESTING_SCOPES)
    async def eliminate_lowest(self, ctx: InteractionContext):
        if poll := await self.bot.poll_cache.get_poll(ctx.target_id):
            await self.eliminate(ctx, poll, highest=False)
        else:
            await ctx.send("This is not a poll.")


def setup(bot):
    Elimination(bot)
