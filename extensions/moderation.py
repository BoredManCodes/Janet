import asyncio
import datetime

from naff import (
    slash_command,
    Permissions,
    OptionTypes,
    InteractionContext,
    slash_option,
    Member,
    BrandColors,
    Embed,
    Button,
    ComponentContext,
    ButtonStyles,
    AutocompleteContext,
    Snowflake_Type,
    EmbedField,
)
from naff.api.events import Component

from extensions.shared import ExtensionBase, OPT_find_poll
from models.poll_default import DefaultPoll


class Moderation(ExtensionBase):
    def __init__(self, _):
        self.close_poll.autocomplete("poll")(self.poll_autocomplete)

    @staticmethod
    def poll_autocomplete_predicate(ctx: AutocompleteContext):
        def predicate(poll: DefaultPoll):
            return not poll.expired

        return predicate

    @slash_command("moderation", description="Moderation commands", default_member_permissions=Permissions.MANAGE_GUILD)
    async def moderation(self, ctx):
        ...

    async def confirmation(
        self, ctx: InteractionContext, title: str, description: str, fields: list[EmbedField] = None
    ) -> None | ComponentContext:
        embed = Embed(title=title, description=description, color=BrandColors.RED)
        buttons = [
            Button(label="Yes", style=ButtonStyles.SUCCESS, custom_id="yes"),
            Button(label="No", style=ButtonStyles.DANGER, custom_id="no"),
        ]
        if fields:
            embed.fields = fields

        prompt = await ctx.send(embed=embed, components=buttons, ephemeral=True)
        try:
            event: Component = await self.bot.wait_for_component(
                messages=[prompt], timeout=20, check=lambda c: c.ctx.author.id == ctx.author.id
            )
            context = event.ctx
            if context.custom_id == "yes":
                await context.defer(edit_origin=True)
                return context
            else:
                embed.description = "Cancelled"
                embed.fields = []
                await context.edit_origin(embed=embed, components=[])
                return None
        except asyncio.TimeoutError:
            await ctx.send("Timed out!", ephemeral=True)
            return None

    @moderation.subcommand("disable_voting", sub_cmd_description="Prevent a user from voting in your server")
    @slash_option("user", "The user to modify", OptionTypes.USER, required=True)
    async def blacklist(self, ctx: InteractionContext, user: Member):
        await ctx.defer(ephemeral=True)
        guild_data = await self.bot.poll_cache.get_guild_data(ctx.guild_id)

        if user.id in guild_data.blacklisted_users:
            if b_ctx := await self.confirmation(
                ctx, "Restore voting permissions?", f"Are you sure you want to allow {user.mention} to vote?"
            ):
                guild_data.blacklisted_users.remove(user.id)
                await self.bot.poll_cache.set_guild_data(guild_data)

                embed = Embed(
                    title="Restored Voting Permissions",
                    description=f"{user.mention} can now vote",
                    color=BrandColors.GREEN,
                )
                await b_ctx.edit_origin(embed=embed, components=[])

                return

        else:
            if b_ctx := await self.confirmation(
                ctx, "Revoke voting permissions?", f"Are you sure you want to disable voting for {user.mention}?"
            ):
                guild_data.blacklisted_users.append(user.id)
                await self.bot.poll_cache.set_guild_data(guild_data)

                embed = Embed(
                    title="Revoked Voting Permissions",
                    description=f"{user.mention} can no longer vote",
                    color=BrandColors.RED,
                )
                await b_ctx.edit_origin(embed=embed, components=[])

                return

    @moderation.subcommand("list_revoked", sub_cmd_description="List users who are not allowed to vote")
    async def list_blacklisted(self, ctx: InteractionContext):
        await ctx.defer(ephemeral=True)
        guild_data = await self.bot.poll_cache.get_guild_data(ctx.guild_id)
        if not guild_data.blacklisted_users:
            await ctx.send("No users have had voting revoked!")
            return

        users = [f"<@{user_id}>" for user_id in guild_data.blacklisted_users]
        embed = Embed(title="Users with revoked voting perms", description=", ".join(users), color=BrandColors.RED)
        await ctx.send(embed=embed)

    @moderation.subcommand("close_poll", sub_cmd_description="Close a poll", options=[OPT_find_poll])
    async def close_poll(self, ctx: InteractionContext, poll: Snowflake_Type):
        await ctx.defer(ephemeral=True)

        if poll := await self.process_poll_option(ctx, poll):
            if b_ctx := await self.confirmation(
                ctx,
                "Close poll?",
                f"Are you sure you want to close poll `{poll.title}`?",
                fields=[EmbedField("Opened By", poll.author_name)],
            ):
                poll._expired = True
                poll.expire_time = datetime.datetime.now()
                asyncio.create_task(poll.update_messages())
                await self.bot.poll_cache.store_poll(poll)

                embed = Embed(title="Poll Closed", description=f"Closed poll `{poll.title}`", color=BrandColors.RED)
                await b_ctx.edit_origin(embed=embed, components=[])

                return


def setup(bot):
    Moderation(bot)
