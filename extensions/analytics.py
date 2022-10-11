import os

from naff import Extension, Context, BrandColors, InteractionContext, Embed, slash_command, listen, Timestamp
from naff.api.events import GuildJoin, GuildLeft

from extensions.shared import get_options_list


class Analytics(Extension):
    # wish.com naff-track
    def __init__(self, bot):
        self.command_usage = {}
        self.option_usage = {}

        self.bot.post_run_callback = self.on_command

        self.hook = None
        self.join_log_id = os.environ.get("JOIN_LOG_ID", None)

    async def async_start(self):
        for command in self.bot.application_commands:
            if "analytics" not in command.resolved_name:
                if command.callback:
                    self.command_usage[command.resolved_name] = 0
        for option in get_options_list(inline_options=True):
            if not option.required:
                self.option_usage[str(option.name)] = 0

    async def on_command(self, ctx: Context, *args, **kwargs):
        if "analytics" not in ctx.command.resolved_name and ctx.command.resolved_name in self.command_usage:
            self.command_usage[ctx.command.resolved_name] += 1
        if kwargs:
            for option in kwargs:
                if option in self.option_usage:
                    self.option_usage[option] += 1

    @slash_command(
        "analytics", description="Get some analytics about the bot", scopes=[985991455074050078, 1013821165191581756]
    )
    async def analytics(self, ctx: InteractionContext):
        ...

    @analytics.subcommand("commands", sub_cmd_description="Get some analytics about the commands")
    async def analytics_cmds(self, ctx: InteractionContext) -> None:
        sorted_dict = dict(sorted(self.command_usage.items(), key=lambda item: item[1], reverse=True))

        await ctx.send(
            embed=Embed(
                title="Command Usage",
                description="\n".join(f"{name}: {count}" for name, count in sorted_dict.items()),
                color=BrandColors.BLURPLE,
            )
        )

    @analytics.subcommand("options", sub_cmd_description="Get some analytics about poll options")
    async def analytics_options(self, ctx: InteractionContext) -> None:
        sorted_dict = dict(sorted(self.option_usage.items(), key=lambda item: item[1], reverse=True))

        await ctx.send(
            embed=Embed(
                title="Option Usage",
                description="\n".join(f"{name}: {count}" for name, count in sorted_dict.items()),
                color=BrandColors.BLURPLE,
            )
        )

    async def get_webhook(self):
        if not self.hook:
            channel = self.bot.get_channel(self.join_log_id)
            hooks = await channel.fetch_webhooks()
            if any(hook.name == "naff-track" for hook in hooks):
                self.hook = next(hook for hook in hooks if hook.name == "naff-track")
            else:
                self.hook = await channel.create_webhook(name="naff-track")
        return self.hook

    @listen()
    async def on_guild_join(self, event: GuildJoin):
        if self.bot.is_ready and self.join_log_id:
            guild_data = await self.bot.poll_cache.get_guild_data(event.guild.id)

            hook = await self.get_webhook()

            embed = Embed("New Guild", color=BrandColors.GREEN)
            embed.add_field("Name", event.guild.name)
            embed.add_field("ID", event.guild.id)
            embed.add_field("Guild Age", Timestamp.from_snowflake(event.guild.id).format("R"))
            embed.add_field("Approx Member Count", event.guild.member_count)
            if guild_data and guild_data.blacklisted:
                embed.add_field("⚠️ Blacklisted Guild", "True")
            if event.guild.icon:
                embed.set_thumbnail(event.guild.icon.url)

            await hook.send(embed=embed, avatar_url=self.bot.user.avatar.url)

    @listen()
    async def on_guild_remove(self, event: GuildLeft):
        if self.bot.is_ready and self.join_log_id:
            hook = await self.get_webhook()

            embed = Embed("Left Guild", color=BrandColors.RED)
            embed.add_field("Name", event.guild.name)
            embed.add_field("ID", event.guild.id)
            embed.add_field("Guild Age", Timestamp.from_snowflake(event.guild.id).format("R"))
            embed.add_field("Aprox Member Count", event.guild.member_count)
            if event.guild.icon:
                embed.set_thumbnail(event.guild.icon.url)

            await hook.send(embed=embed, avatar_url=self.bot.user.avatar.url)


def setup(bot):
    Analytics(bot)
