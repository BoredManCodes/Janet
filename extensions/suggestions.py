import datetime
import logging
import uuid
from enum import IntEnum

import attr
from apscheduler.triggers.date import DateTrigger
from naff import (
    Snowflake_Type,
    Embed,
    slash_command,
    Modal,
    ShortText,
    ParagraphText,
    InteractionContext,
    ModalContext,
    Button,
    ButtonStyles,
    listen,
    BrandColors,
    Permissions,
    slash_option,
    OptionTypes,
    GuildChannel,
    MessageableMixin,
    Timestamp,
    context_menu,
    CommandTypes,
    EMBED_FIELD_VALUE_LENGTH,
    GuildText,
)
from naff.api.events import ButtonPressed
from naff.client.errors import NotFound, Forbidden, HTTPException
from naff.client.utils import no_export_meta
from naff.models.discord.base import ClientObject

from extensions.shared import ExtensionBase

log = logging.getLogger("Inquiry")


class SuggestionVote(IntEnum):
    """The vote for a suggestion."""

    added = 1
    removed = -1

    def __str__(self) -> str:
        return self.name.title()


@attr.s(auto_attribs=True, on_setattr=[attr.setters.convert, attr.setters.validate], kw_only=True)
class Suggestion(ClientObject):
    id: str = attr.ib(factory=uuid.uuid4, converter=str)
    text: str
    description: str = attr.ib(default=None)
    author_id: Snowflake_Type = attr.ib(default=None)
    message_id: Snowflake_Type = attr.ib(default=None)

    upvotes: set[Snowflake_Type] = attr.ib(factory=set, converter=set)
    downvotes: set[Snowflake_Type] = attr.ib(factory=set, converter=set)

    admin_response: str = attr.ib(default=None)
    admin_accepted: None | bool = attr.ib(default=None)

    edit_context: InteractionContext | None = attr.ib(default=None, metadata=no_export_meta)

    @property
    def score(self) -> int:
        return len(self.upvotes) - len(self.downvotes)

    @property
    def score_emoji(self) -> str:
        if self.score == 0:
            return "➖"
        return "🔼" if self.score > 0 else "🔽"

    @property
    def components(self) -> list[Button]:
        disabled = self.admin_accepted is not None
        return [
            Button(ButtonStyles.SUCCESS, emoji="🔼", custom_id="suggestion|upvote", disabled=disabled),
            Button(ButtonStyles.DANGER, emoji="🔽", custom_id="suggestion|downvote", disabled=disabled),
            Button(ButtonStyles.SECONDARY, emoji="❔", custom_id="suggestion|help"),
        ]

    def cast_upvote(self, user_id: Snowflake_Type) -> SuggestionVote:
        if user_id in self.downvotes:
            self.downvotes.remove(user_id)

        if user_id in self.upvotes:
            self.upvotes.remove(user_id)
            return SuggestionVote.removed
        else:
            self.upvotes.add(user_id)
            return SuggestionVote.added

    def cast_downvote(self, user_id: Snowflake_Type) -> SuggestionVote:
        if user_id in self.upvotes:
            self.upvotes.remove(user_id)

        if user_id in self.downvotes:
            self.downvotes.remove(user_id)
            return SuggestionVote.removed
        else:
            self.downvotes.add(user_id)
            return SuggestionVote.added

    async def generate_embed(self) -> Embed:
        embed = Embed(title=self.text, description=self.description)
        embed.add_field(name=f"{self.score_emoji} Score", value=self.score)
        embed.set_footer(text="Suggestion Poll", icon_url=self._client.user.avatar.url)

        if self.admin_accepted is not None:
            if self.admin_accepted:
                embed.color = BrandColors.GREEN
                embed.set_footer(text="Accepted", icon_url=self._client.user.avatar.url)
            else:
                embed.color = BrandColors.RED
                embed.set_footer(text="Rejected", icon_url=self._client.user.avatar.url)
        else:
            embed.color = BrandColors.BLURPLE

        if self.admin_response:
            embed.add_field(name="Admin Response", value=self.admin_response)

        author = await self._client.cache.fetch_user(self.author_id)
        embed.set_author(name=author.username, icon_url=author.avatar.url)

        return embed

    async def update_message(self, channel_id: Snowflake_Type) -> None:
        message = await self._client.cache.fetch_message(channel_id, self.message_id)
        interaction_context = None

        if self.edit_context:
            age = (Timestamp.now() - Timestamp.from_snowflake(self.edit_context.interaction_id)).total_seconds()
            if age < 890:  # 15 minutes minus 10 seconds
                interaction_context = self.edit_context

        try:
            embed = await self.generate_embed()
            try:
                await message.edit(embeds=embed, components=self.components, context=interaction_context)
            except (NotFound, Forbidden, HTTPException):
                if interaction_context:
                    await message.edit(embeds=embed, components=self.components)
                    return
                raise
        except NotFound:
            log.warning(f"Suggestion Message {self.message_id} not found -- likely deleted by user")
        except Forbidden:
            log.warning(
                f"Suggestion {self.message_id} in channel {channel_id} cannot be edited -- likely permissions issue"
            )


class Suggestions(ExtensionBase):
    async def get_suggestion(self, message_id: Snowflake_Type) -> Suggestion:
        return await self.bot.poll_cache.get_suggestion(message_id)

    async def __update(self, message_id: Snowflake_Type, channel_id: Snowflake_Type = None):
        suggestion = await self.get_suggestion(message_id)
        if suggestion:
            await suggestion.update_message(channel_id)

    def schedule_update(self, context: InteractionContext):
        bot_scheduler = self.bot.scheduler
        message_id = context.message.id if context.message else context.target_id
        channel_id = context.channel.id
        job_id = f"suggestion|{message_id}"

        if bot_scheduler.get_job(job_id):
            return
        bot_scheduler.add_job(
            self.__update,
            trigger=DateTrigger(datetime.datetime.now() + datetime.timedelta(seconds=2)),
            id=job_id,
            args=[message_id, channel_id],
        )
        log.debug(f"Scheduled update for suggestion {message_id}")

    @listen()
    async def on_button(self, event: ButtonPressed):
        ctx = event.ctx

        if ctx.custom_id == "suggestion|upvote":
            suggestion = await self.get_suggestion(ctx.message.id)
            vote = suggestion.cast_upvote(ctx.author.id)

            await ctx.send(f"Upvote {vote}!", ephemeral=True)
            self.schedule_update(ctx)
        elif ctx.custom_id == "suggestion|downvote":
            suggestion = await self.get_suggestion(ctx.message.id)
            vote = suggestion.cast_downvote(ctx.author.id)

            await ctx.send(f"Downvote {vote}!", ephemeral=True)
            self.schedule_update(ctx)
        elif ctx.custom_id == "suggestion|help":
            suggestion = await self.get_suggestion(ctx.message.id)
            if suggestion and suggestion.admin_accepted is not None:
                if suggestion.admin_accepted:
                    await ctx.send("This suggestion has been accepted!", ephemeral=True)
                else:
                    await ctx.send("This suggestion has been rejected!", ephemeral=True)
            else:
                await ctx.send(
                    "Use the buttons above to upvote or downvote this suggestion.\nAn Admin can approve or deny this suggestion using context menu commands",
                    ephemeral=True,
                )

    @slash_command(
        "setup-suggestions",
        description="Setup the suggestions channel",
        default_member_permissions=Permissions.MANAGE_CHANNELS,
    )
    @slash_option("channel", "The channel to send suggestions to", opt_type=OptionTypes.CHANNEL, required=True)
    async def setup_suggestions(self, ctx: InteractionContext, channel: GuildChannel):
        if not isinstance(channel, MessageableMixin):
            return await ctx.send("You must provide a messageable channel", ephemeral=True)
        channel: GuildText

        await ctx.defer(ephemeral=True)
        channel_perms = channel.permissions_for(ctx.guild.me)
        if not channel_perms.SEND_MESSAGES:
            return await ctx.send("I am missing permissions to send messages in that channel", ephemeral=True)
        if not channel_perms.MANAGE_MESSAGES:
            return await ctx.send("I am missing permissions to manage messages in that channel", ephemeral=True)

        guild_data = await self.bot.poll_cache.get_guild_data(ctx.guild.id)
        guild_data.suggestion_channel = channel.id
        await self.bot.poll_cache.set_guild_data(guild_data)
        await ctx.send(
            f"Suggestions channel set to {channel.mention}\nRemember to enable the suggest command in your Server's Integration settings",
            ephemeral=True,
        )

    @slash_command(name="suggest", description="Suggest something", default_member_permissions=Permissions.NONE)
    async def suggest(self, ctx: InteractionContext):
        guild_data = await self.bot.poll_cache.get_guild_data(ctx.guild_id)

        if not guild_data.suggestion_channel:
            return await ctx.send(
                f"There is no suggestion channel set up for this server - Ask a server admin to use {self.setup_suggestions.mention()}",
                ephemeral=True,
            )

        suggestion_channel = await self.bot.cache.fetch_channel(guild_data.suggestion_channel)

        if not suggestion_channel:
            return await ctx.send(
                f"There is no suggestion channel set up for this server - Ask a server admin to use {self.setup_suggestions.mention()}",
                ephemeral=True,
            )

        modal = Modal(
            title="Suggest something",
            components=[
                ShortText(
                    label="Suggestion Title",
                    placeholder="A short title for your suggestion",
                    required=True,
                    custom_id="title",
                ),
                ParagraphText(
                    label="Suggestion Description",
                    placeholder="A longer description for your suggestion",
                    required=False,
                    custom_id="description",
                ),
            ],
        )
        await ctx.send_modal(modal)
        m_ctx: ModalContext = await ctx.bot.wait_for_modal(modal, ctx.author, timeout=60 * 5)
        if not m_ctx:
            return await ctx.send("You took too long to respond", ephemeral=True)

        await m_ctx.defer(ephemeral=True)
        suggestion = Suggestion(
            text=m_ctx.responses["title"],
            description=m_ctx.responses["description"],
            author_id=ctx.author.id,
            client=self.bot,
        )
        message = await suggestion_channel.send(
            embed=await suggestion.generate_embed(), components=suggestion.components
        )
        suggestion.message_id = message.id
        await self.bot.poll_cache.set_suggestion(suggestion, store=True)
        await m_ctx.send(f"[Suggestion sent!]({message.jump_url})", ephemeral=True)

    @context_menu("suggestion_deny", CommandTypes.MESSAGE, default_member_permissions=Permissions.ADMINISTRATOR)
    async def deny_suggestion(self, ctx: InteractionContext):
        suggestion = await self.get_suggestion(ctx.target_id)
        if not suggestion:
            return await ctx.send("This is not a suggestion", ephemeral=True)

        modal = Modal(
            "Deny Reason",
            components=[
                ParagraphText(
                    label="Reason",
                    custom_id="reason",
                    placeholder="Optionally provide a reason for denying this suggestion",
                    required=False,
                    max_length=EMBED_FIELD_VALUE_LENGTH,
                )
            ],
        )
        await ctx.send_modal(modal)
        m_ctx: ModalContext = await ctx.bot.wait_for_modal(modal, ctx.author, timeout=60)
        if m_ctx:
            await m_ctx.send("Suggestion denied", ephemeral=True)

            suggestion.admin_accepted = False
            if m_ctx.responses["reason"]:
                suggestion.admin_response = m_ctx.responses["reason"]
            await self.bot.poll_cache.set_suggestion(suggestion, store=True)
            self.schedule_update(ctx)

    @context_menu("suggestion_approve", CommandTypes.MESSAGE, default_member_permissions=Permissions.ADMINISTRATOR)
    async def approve_suggestion(self, ctx: InteractionContext):
        suggestion = await self.get_suggestion(ctx.target_id)
        if not suggestion:
            return await ctx.send("This is not a suggestion", ephemeral=True)

        modal = Modal(
            "Approve Reason",
            components=[
                ParagraphText(
                    label="Reason",
                    custom_id="reason",
                    placeholder="Optionally provide a reason for approving this suggestion",
                    required=False,
                    max_length=EMBED_FIELD_VALUE_LENGTH,
                )
            ],
        )
        await ctx.send_modal(modal)
        m_ctx: ModalContext = await ctx.bot.wait_for_modal(modal, ctx.author, timeout=60)
        if m_ctx:
            await m_ctx.send("Suggestion approved", ephemeral=True)

            suggestion.admin_accepted = True
            if m_ctx.responses["reason"]:
                suggestion.admin_response = m_ctx.responses["reason"]
            await self.bot.poll_cache.set_suggestion(suggestion, store=True)
            self.schedule_update(ctx)


def setup(bot):
    Suggestions(bot)
