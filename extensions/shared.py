import textwrap
from typing import TYPE_CHECKING

from naff import (
    InteractionContext,
    to_snowflake,
    Extension,
    AutocompleteContext,
    Timestamp,
    SlashCommandOption,
    OptionTypes,
    MaterialColors,
    SlashCommandChoice,
    Permissions,
)
from thefuzz import fuzz, process

from models.poll import PollData

if TYPE_CHECKING:
    from main import Bot

__all__ = ("ExtensionBase", "OPT_find_poll", "OPT_find_option", "colours", "def_options")

OPT_find_poll = SlashCommandOption(
    name="poll",
    description="The poll to edit",
    type=OptionTypes.STRING,
    required=True,
    autocomplete=True,
)

OPT_find_option = SlashCommandOption(
    name="option",
    description="The option to remove",
    type=OptionTypes.STRING,
    required=True,
    autocomplete=True,
)

colours = sorted(
    [MaterialColors(c).name.title() for c in MaterialColors]
    + [
        "Blurple",
        "Fuchsia",
        "White",
        "Black",
    ]
)

def_options = [
    SlashCommandOption(
        "title",
        OptionTypes.STRING,
        "The title for your poll",
        required=True,
        max_length=100,
    ),
    SlashCommandOption(
        "colour",
        OptionTypes.STRING,
        "Choose the colour of the embed (default 'blurple')",
        choices=[SlashCommandChoice(c.replace("_", " "), c) for c in colours],
        required=False,
    ),
    SlashCommandOption(
        "description",
        OptionTypes.STRING,
        "The description for your poll",
        required=False,
        max_length=512,
    ),
    SlashCommandOption(
        "duration",
        OptionTypes.STRING,
        "Choose the duration of the poll (example: '1w 3d 7h 5m 20s')",
        required=False,
    ),
    SlashCommandOption(
        "max_votes",
        OptionTypes.INTEGER,
        "The maximum number of votes per user (default unlimited)",
        min_value=1,
        required=False,
    ),
    SlashCommandOption(
        "voting_role",
        OptionTypes.ROLE,
        "Restrict voting to this role (default unrestricted)",
        required=False,
    ),
    SlashCommandOption(
        "hide_results",
        OptionTypes.BOOLEAN,
        "Hide results until the poll is closed (default False)",
        required=False,
    ),
    SlashCommandOption(
        "anonymous",
        OptionTypes.BOOLEAN,
        "Prevent anyone from seeing who voted for what (default False)",
        required=False,
    ),
    SlashCommandOption(
        "open_poll",
        OptionTypes.BOOLEAN,
        "Allow anybody to add options to the poll (default False)",
        required=False,
    ),
    SlashCommandOption(
        "thread",
        OptionTypes.BOOLEAN,
        "Create a thread attached to this poll.",
        required=False,
    ),
    SlashCommandOption(
        "proportional_results",
        OptionTypes.BOOLEAN,
        "Show the proportion of voters who voted for each option (default False)",
        required=False,
    ),
    SlashCommandOption(
        "inline",
        OptionTypes.BOOLEAN,
        "Make options appear inline, in the embed (default False)",
        required=False,
    ),
    SlashCommandOption(
        "image",
        OptionTypes.ATTACHMENT,
        "Attach an image to the embed",
        required=False,
    ),
    SlashCommandOption(
        "close_message",
        OptionTypes.BOOLEAN,
        "Send a message when the poll is closed (default False)",
        required=False,
    ),
]


class ExtensionBase(Extension):
    bot: "Bot"

    async def process_poll_option(self, ctx: InteractionContext, poll: str) -> PollData | None:
        try:
            poll = await self.bot.poll_cache.get_poll(to_snowflake(poll))
        except AttributeError as e:
            pass
        finally:
            if not isinstance(poll, PollData):
                await ctx.send("Unable to find the requested poll!")
                return None
            return poll

    @staticmethod
    def poll_autocomplete_predicate(ctx: AutocompleteContext):
        def predicate(poll: PollData):
            if poll.author_id == ctx.author.id:
                return True
            if ctx.author.has_permission(Permissions.MANAGE_MESSAGES):
                return True
            return False

        return predicate

    async def poll_autocomplete(self, ctx: AutocompleteContext, **kwargs) -> bool:
        predicate = self.poll_autocomplete_predicate(ctx)

        polls = await self.bot.poll_cache.get_polls_by_guild(ctx.guild_id)
        polls.sort(key=lambda x: x.message_id, reverse=True)

        if polls:
            if not ctx.input_text:
                results = [p for p in polls if predicate(p)][:25]
            else:
                results = process.extract(
                    ctx.input_text, {p.message_id: p.title for p in polls if predicate(p)}, limit=25
                )
                results = [await self.bot.poll_cache.get_poll(p[2]) for p in results if p[1] > 50]

            await ctx.send(
                [
                    {
                        "name": f"{textwrap.shorten(p.title, width=65)} ({Timestamp.from_snowflake(p.message_id).ctime()})",
                        "value": str(p.message_id),
                    }
                    for p in results
                ]
            )

        else:
            await ctx.send([])

    async def option_autocomplete(self, ctx: AutocompleteContext, **kwargs) -> None:
        poll = await self.bot.poll_cache.get_poll(to_snowflake(kwargs.get("poll")))
        if poll:
            p_options = list(poll.poll_options)
            p_options = sorted(
                p_options,
                key=lambda x: fuzz.partial_ratio(x.text, ctx.input_text),
                reverse=True,
            )[:25]

            await ctx.send([p.text for p in p_options])

        else:
            await ctx.send([])
