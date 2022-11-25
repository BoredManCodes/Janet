import textwrap
from typing import Union

from naff import (
    Member,
    EmbedField,
    ActionRow,
    Button,
    ButtonStyles,
    spread_to_rows,
    InteractionContext,
    EMBED_MAX_NAME_LENGTH,
    Embed,
)

from models.emoji import default_emoji
from models.poll_default import DefaultPoll
from models.poll_option import PollOption


class EliminationPoll(DefaultPoll):
    @classmethod
    async def from_ctx(cls, *args, **kwargs) -> Union["DefaultPoll", bool]:
        new_cls = await super().from_ctx(*args, **kwargs)
        new_cls.poll_type = "elimination"
        return new_cls

    def get_components(self, *, disable: bool = False) -> list[ActionRow]:
        if self.expired and not disable:
            return []
        buttons = []
        for i in range(len(self.poll_options)):
            buttons.append(
                Button(
                    1,
                    emoji=self.poll_options[i].emoji,
                    custom_id=f"poll_option|{i}",
                    disabled=self.expired or self.poll_options[i].eliminated,
                ),
            )
        if self.open_poll and len(self.poll_options) < len(default_emoji):
            buttons.append(
                Button(ButtonStyles.SUCCESS, emoji="\U00002795", custom_id="add_option", disabled=self.expired)
            )
        return spread_to_rows(*buttons)

    def get_option_fields(self, **kwargs) -> list[EmbedField]:
        fields = []
        for option in self.poll_options:
            name = textwrap.shorten(f"{option.emoji} {option.text}", width=EMBED_MAX_NAME_LENGTH)

            if option.eliminated:
                voter_id = next(iter(option.voters))
                if self.anonymous:
                    fields.append(EmbedField(name, "Eliminated by an anonymous voter", False))
                else:
                    fields.append(EmbedField(name=name, value=f"Eliminated by <@{voter_id}>", inline=False))
            else:
                fields.append(EmbedField(name=name, value=f"Available", inline=False))
        return fields

    @property
    def close_embed(self) -> Embed:
        embed = Embed(
            title="Poll Closed",
            description="This poll has been closed",
            color=self.get_colour(),
        )
        embed.add_field(name="Poll Name", value=self.title, inline=False)
        remaining = [o for o in self.poll_options if not o.eliminated]
        if remaining:
            embed.add_field(
                name="Remaining Options", value="\n".join([f"{o.emoji} {o.text}" for o in remaining]), inline=False
            )
        else:
            embed.add_field(name="Remaining Options", value="None", inline=False)

        embed.set_footer(text=f"Poll ID: {self.message_id}")
        return embed

    @property
    def vote_added_text(self) -> str:
        return "Option eliminated!"

    @property
    def vote_removed_text(self) -> str:
        return "Elimination redacted!"

    async def _vote_check(self, ctx: InteractionContext, option: PollOption) -> bool:
        if option.eliminated:
            await ctx.send("This option has already been eliminated!", ephemeral=True)
            return False
        return True

    def _vote(self, option: PollOption, user: Member) -> bool:
        option.eliminated = option.vote(user.id)
        return option.eliminated
