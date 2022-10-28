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

__all__ = ("ExtensionBase", "OPT_find_poll", "OPT_find_option", "colours", "get_options_list")

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

OPT_TITLE = SlashCommandOption(
    "title",
    OptionTypes.STRING,
    "The title for your poll",
    required=True,
    max_length=100,
)
OPT_DESCRIPTION = SlashCommandOption(
    "description",
    OptionTypes.STRING,
    "The description for your poll",
    required=False,
    max_length=512,
)
OPT_PRESET = SlashCommandOption(
    "preset_options",
    OptionTypes.STRING,
    "Use preset options for your poll",
    choices=[
        SlashCommandChoice("`Yes` and `No`", "boolean"),
        SlashCommandChoice("Agree, Disagree, Neutral", "opinion"),
        SlashCommandChoice("Days of the week", "week"),
        SlashCommandChoice("Months of the year", "month"),
        SlashCommandChoice("1-10", "rating"),
        SlashCommandChoice("1-5", "rating_5"),
    ],
    required=False,
)
OPT_COLOUR = SlashCommandOption(
    "colour",
    OptionTypes.STRING,
    "Choose the colour of the embed (default 'blurple')",
    choices=[SlashCommandChoice(c.replace("_", " "), c) for c in colours],
    required=False,
)
OPT_DURATION = SlashCommandOption(
    "duration",
    OptionTypes.STRING,
    "Choose the duration of the poll (example: '1w 3d 7h 5m 20s')",
    required=False,
)
OPT_MAX_VOTES = SlashCommandOption(
    "max_votes",
    OptionTypes.INTEGER,
    "The maximum number of votes per user (default unlimited)",
    min_value=1,
    required=False,
)
OPT_VOTING_ROLE = SlashCommandOption(
    "voting_role",
    OptionTypes.ROLE,
    "Restrict voting to this role (default unrestricted)",
    required=False,
)
OPT_VIEW_RESULTS = SlashCommandOption(
    "view_results",
    OptionTypes.STRING,
    "Choose when to show the results (default 'always')",
    choices=[
        SlashCommandChoice("Always", "always"),
        SlashCommandChoice("Show results to voters", "after_voting"),
        SlashCommandChoice("After the poll has closed", "after_voting_closed"),
    ],
    required=False,
)
OPT_ANONYMOUS = SlashCommandOption(
    "anonymous",
    OptionTypes.BOOLEAN,
    "Prevent anyone from seeing who voted for what (default False)",
    required=False,
)
OPT_OPEN_POLL = SlashCommandOption(
    "open_poll",
    OptionTypes.BOOLEAN,
    "Allow anybody to add options to the poll (default False)",
    required=False,
)
OPT_SHOW_OPTION_AUTHOR = SlashCommandOption(
    "show_option_author",
    OptionTypes.BOOLEAN,
    "Show who added each option (default False)",
    required=False,
)
OPT_THREAD = SlashCommandOption(
    "thread",
    OptionTypes.BOOLEAN,
    "Create a thread attached to this poll.",
    required=False,
)
OPT_PROPORTIONAL = SlashCommandOption(
    "proportional_results",
    OptionTypes.BOOLEAN,
    "Show the proportion of voters who voted for each option (default False)",
    required=False,
)
OPT_INLINE = SlashCommandOption(
    "inline",
    OptionTypes.BOOLEAN,
    "Make options appear inline, in the embed (default False)",
    required=False,
)
OPT_IMAGE = SlashCommandOption(
    "image",
    OptionTypes.ATTACHMENT,
    "Attach an image to the embed",
    required=False,
)
OPT_CLOSE_MESSAGE = SlashCommandOption(
    "close_message",
    OptionTypes.BOOLEAN,
    "Send a message when the poll is closed (default False)",
    required=False,
)
OPT_INLINE_OPTIONS = SlashCommandOption(
    "options",
    OptionTypes.STRING,
    "Options for your poll. Separated with `|`. ie 'opt1 | opt2 | opt3'",
    required=True,
)

get_options_list = [
    OPT_TITLE,
    OPT_DESCRIPTION,
    OPT_PRESET,
    OPT_COLOUR,
    OPT_DURATION,
    OPT_MAX_VOTES,
    OPT_VOTING_ROLE,
    OPT_VIEW_RESULTS,
    OPT_ANONYMOUS,
    OPT_OPEN_POLL,
    OPT_SHOW_OPTION_AUTHOR,
    OPT_THREAD,
    OPT_PROPORTIONAL,
    OPT_INLINE,
    OPT_IMAGE,
    OPT_CLOSE_MESSAGE,
]


def get_options_list(
    title: bool = True,
    inline_options: bool = False,
    description: bool = True,
    preset: bool = True,
    colour: bool = True,
    duration: bool = True,
    max_votes: bool = True,
    voting_role: bool = True,
    view_results: bool = True,
    anonymous: bool = True,
    open_poll: bool = True,
    show_option_author: bool = True,
    thread: bool = True,
    proportional: bool = True,
    inline: bool = True,
    image: bool = True,
    close_message: bool = True,
) -> list[SlashCommandOption]:
    to_process = locals()

    options = []
    for option, state in to_process.copy().items():
        if state is True:
            try:
                _o = eval(f"OPT_{option.upper()}")
                options.append(_o)
            except NameError:
                pass
    return options


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
        if kwargs.get("poll"):
            poll = await self.bot.poll_cache.get_poll(to_snowflake(kwargs.get("poll")))
            if poll:
                p_options = list(poll.poll_options)
                p_options = sorted(
                    p_options,
                    key=lambda x: fuzz.partial_ratio(x.text, ctx.input_text),
                    reverse=True,
                )[:25]

                return await ctx.send([p.text for p in p_options])

        await ctx.send([])
