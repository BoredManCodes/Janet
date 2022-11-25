from naff import (
    slash_command,
    InteractionContext,
    Embed,
    BrandColors,
    Button,
    ButtonStyles,
    component_callback,
    ComponentContext,
)
from naff.client.utils import get

from extensions.shared import ExtensionBase


class InquiryServer(ExtensionBase):
    @slash_command("init", description="Initialize reaction roles", scopes=[1013821165191581756, 985991455074050078])
    async def init(self, ctx: InteractionContext) -> None:
        await ctx.defer()
        poll_ping = get(ctx.guild.roles, name="poll_pings")
        news_ping = get(ctx.guild.roles, name="news_pings")
        preview_ping = get(ctx.guild.roles, name="preview_pings")

        if not poll_ping:
            poll_ping = await ctx.guild.create_role(name="poll_pings")
        if not news_ping:
            news_ping = await ctx.guild.create_role(name="news_pings")
        if not preview_ping:
            preview_ping = await ctx.guild.create_role(name="preview_pings")

        embed = Embed(
            "Roles", description="Press the buttons below to get pinged for polls and news!", color=BrandColors.BLURPLE
        )
        await ctx.send(
            embed=embed,
            components=[
                Button(label="Poll Pings", custom_id="poll_pings", style=ButtonStyles.PRIMARY, emoji="📊"),
                Button(label="News Pings", custom_id="news_pings", style=ButtonStyles.PRIMARY, emoji="📰"),
                Button(label="Preview Pings", custom_id="preview_pings", style=ButtonStyles.PRIMARY, emoji="🔮"),
            ],
        )

    @component_callback("poll_pings")
    async def poll_pings(self, ctx: ComponentContext) -> None:
        await ctx.defer(ephemeral=True)
        poll_ping = get(ctx.guild.roles, name="poll_pings")

        if poll_ping in ctx.author.roles:
            await ctx.author.remove_role(poll_ping)
            await ctx.send("Removed poll pings!")
        else:
            await ctx.author.add_role(poll_ping)
            await ctx.send("Added poll pings!")

    @component_callback("news_pings")
    async def news_pings(self, ctx: ComponentContext) -> None:
        await ctx.defer(ephemeral=True)
        news_ping = get(ctx.guild.roles, name="news_pings")

        if news_ping in ctx.author.roles:
            await ctx.author.remove_role(news_ping)
            await ctx.send("Removed news pings!")
        else:
            await ctx.author.add_role(news_ping)
            await ctx.send("Added news pings!")

    @component_callback("preview_pings")
    async def preview_pings(self, ctx: ComponentContext) -> None:
        await ctx.defer(ephemeral=True)
        preview_ping = get(ctx.guild.roles, name="preview_pings")

        if preview_ping in ctx.author.roles:
            await ctx.author.remove_role(preview_ping)
            await ctx.send("Removed preview pings!")
        else:
            await ctx.author.add_role(preview_ping)
            await ctx.send("Added preview pings!")


def setup(bot):
    InquiryServer(bot)
