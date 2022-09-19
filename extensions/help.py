import attrs
from naff import Extension, slash_command, InteractionContext, AutocompleteContext, slash_option, Embed, BrandColours
from thefuzz import process
import yaml


@attrs.define
class HelpTopic:
    """An object representing a help topic and its data"""

    title: str = attrs.field()
    brief: str = attrs.field()

    content: str = attrs.field()
    image: str | None = attrs.field(default=None)


class HelpExtension(Extension):
    def __init__(self, *args, **kwargs):
        self.topics: dict[str, HelpTopic] = {}

        with open("data/help.yml", encoding="UTF-8") as f:
            data = yaml.safe_load(f)
            for topic, value in data.items():
                self.topics[topic] = HelpTopic(**value)

    @slash_command("help", description="Get help with the bot")
    @slash_option("topic", description="The topic to get help with", opt_type=3, required=False)
    async def help_main(self, ctx: InteractionContext, topic: str | None = None) -> None:
        if topic:
            if topic in self.topics:
                embed = Embed(
                    title=self.topics[topic].title, description=self.topics[topic].content, color=BrandColours.BLURPLE
                )
                if self.topics[topic].image:
                    embed.set_image(url=self.topics[topic].image)
                await ctx.send(embed=embed)

            else:
                await ctx.send(f"Unable to find the requested help topic: {topic}")
        else:
            embed = Embed(
                title="Help Topics",
                description="Use `/help <topic>` to get help with a specific topic.\n\n",
                color=BrandColours.BLURPLE,
            )
            sorted_topics = sorted(self.topics.values(), key=lambda t: t.title)

            for topic in sorted_topics:
                embed.add_field(name=topic.title, value=topic.brief, inline=False)

            embed.set_footer(
                text="Think we need a new help topic? Let us know! Use `/feedback` to send us feedback.",
                icon_url=self.bot.user.avatar.url,
            )

            await ctx.send(embed=embed)

    @help_main.autocomplete("topic")
    async def help_topic_auto_complete(self, ctx: AutocompleteContext, **kwargs) -> None:
        """Autocomplete for the help topic"""
        if not ctx.input_text:
            results = list(self.topics.keys())[:25]
        else:
            results = process.extract(ctx.input_text, self.topics.keys(), limit=25)
            results = [r[0] for r in results if r[1] > 50]

        await ctx.send(results)


def setup(bot):
    HelpExtension(bot)
