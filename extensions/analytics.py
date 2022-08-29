from naff import Extension, Context, BrandColors, InteractionContext, Embed, slash_command

from extensions.shared import def_options as poll_options


class Analytics(Extension):
    # wish.com naff-track
    def __init__(self, bot):
        self.command_usage = {}
        self.option_usage = {}

        self.bot.post_run_callback = self.on_command

    async def async_start(self):
        for command in self.bot.application_commands:
            if "analytics" not in command.resolved_name:
                if command.callback:
                    self.command_usage[command.resolved_name] = 0
        for option in poll_options:
            if not option.required:
                self.option_usage[str(option.name)] = 0

    async def on_command(self, ctx: Context, *args, **kwargs):
        if "analytics" not in ctx.command.resolved_name:
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


def setup(bot):
    Analytics(bot)
