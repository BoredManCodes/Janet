import asyncio
import datetime
import logging
import random
import signal
import time
from copy import deepcopy
from typing import Any

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from naff import (
    Client,
    Intents,
    listen,
    MISSING,
    ComponentContext,
    Snowflake_Type,
    IntervalTrigger,
    Task,
    Modal,
    ShortText,
    CommandTypes,
    InteractionContext,
    ThreadChannel,
    Status,
    BrandColors,
    Embed,
)
from naff.api.events import Button, ModalResponse, GuildLeft, GuildJoin
from naff.api.events.processors._template import Processor
from naff.client.errors import NotFound
from naff.models.naff.application_commands import context_menu, slash_command

from models.poll import PollData, sanity_check
from poll_cache import PollCache

__all__ = ("Bot",)

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger("Inquiry")

ap_log = logging.getLogger("apscheduler")
ap_log.setLevel(logging.WARNING)


class Bot(Client):
    def __init__(self) -> None:
        super().__init__(
            intents=Intents.new(guilds=True, reactions=True, default=False),
            sync_interactions=True,
            delete_unused_application_cmds=False,
            activity="with an update...",
            status=Status.DND,
        )
        self.poll_cache: PollCache = MISSING

        self.update_lock = asyncio.Lock()  # prevent concurrent updates

        self.scheduler = AsyncIOScheduler()

        # disable processors that we don't need for efficiency
        # naff by default will request missing data, by removing these, the api won't be polled on every reaction
        del self.processors["raw_message_reaction_remove"]
        del self.processors["raw_message_reaction_remove_all"]

    @Processor.define()
    async def _on_raw_message_reaction_add(self, event: "RawGatewayEvent") -> None:
        poll = await self.poll_cache.get_poll(event.data["message_id"])
        data = event.data
        if poll:
            if data["emoji"]["name"] in ("🔴", "🛑", "🚫", "⛔"):
                if int(data["user_id"]) == poll.author_id:
                    log.info(f"Closing poll {poll.message_id} due to reaction")
                    await self.close_poll(poll.message_id)
        if member := event.data.get("member"):
            self.cache.place_member_data(event.data.get("guild_id"), member)

    @classmethod
    async def run(cls, token: str) -> None:
        bot = cls()

        signal.signal(signal.SIGINT, lambda *_: asyncio.create_task(bot.stop()))
        signal.signal(signal.SIGTERM, lambda *_: asyncio.create_task(bot.stop()))

        bot.load_extension("extensions.dev")
        bot.load_extension("extensions.create_poll")
        bot.load_extension("extensions.edit_poll")
        bot.load_extension("extensions.poll_utils")
        bot.load_extension("extensions.admin")
        bot.load_extension("extensions.bot_lists")
        bot.load_extension("extensions.help")
        bot.load_extension("extensions.analytics")
        bot.load_extension("extensions.moderation")

        for command in bot.application_commands:
            # it really isnt necessary to do it like this, but im really lazy
            # basically this disables using every command in dms **except** the commands in this file
            command.dm_permission = False

        bot.poll_cache = await PollCache.initialize(bot)

        bot.scheduler.start()

        await bot.astart(token)

    async def set_poll(self, poll: PollData) -> None:
        await self.poll_cache.store_poll(poll)

    @listen()
    async def on_startup(self) -> Any:
        await self.poll_cache.ready.wait()
        log.info(f"Logged in as {self.user.username}")
        log.info(f"Currently in {len(self.guilds)} guilds")
        await self.change_presence(activity="with polls", status=Status.ONLINE)

    async def stop(self) -> None:
        log.info("Stopping...")
        self.scheduler.shutdown()
        await self.poll_cache.stop()
        await super().stop()

    @slash_command("invite", description="Get the invite link for this bot")
    async def invite(self, ctx: InteractionContext):
        await ctx.send(
            f"https://discord.com/api/oauth2/authorize?client_id={self.app.id}&permissions=377957124096&scope=bot%20applications.commands"
        )

    @slash_command("server", description="Join the support server")
    async def server(self, ctx: InteractionContext) -> None:
        await ctx.send("https://discord.gg/vtRTAwmQsH")

    @slash_command("feedback", description="Send feedback to the bot owner")
    async def feedback(self, ctx: InteractionContext):
        await ctx.send("Thank you!\nhttps://forms.gle/6NDMJQXqmWL8fQVm6")

    @listen()
    async def on_modal_response(self, event: ModalResponse) -> Any:
        ctx = event.context
        ids = ctx.custom_id.split("|")
        if len(ids) == 2:
            await ctx.defer(ephemeral=True)
            if not await sanity_check(ctx):
                return

            message_id = ctx.custom_id.split("|")[1]
            if poll := await self.poll_cache.get_poll(message_id):
                async with poll.lock:
                    poll.add_option(ctx.responses["new_option"])

                    self.schedule_update(poll.message_id)
                log.info(f"Added option to {message_id}")
                return await ctx.send(f"Added {ctx.responses['new_option']} to the poll")
            return await ctx.send("That poll could not be edited")

    @listen()
    async def on_button(self, event: Button) -> Any:
        ctx: ComponentContext = event.context

        guild_data = await self.poll_cache.get_guild_data(ctx.guild.id)
        if guild_data.blacklisted_users:
            if ctx.author.id in guild_data.blacklisted_users:
                return await ctx.send("This server's moderators have disabled your ability to vote", ephemeral=True)

        if isinstance(ctx.channel, ThreadChannel):
            message_id = ctx.channel.id
        else:
            message_id = ctx.message.id

        if ctx.custom_id == "add_option":
            if poll := await self.poll_cache.get_poll(message_id):
                if poll.voting_role:
                    if not ctx.author.has_role(poll.voting_role):
                        return await ctx.send("You do not have permission to add options to this poll", ephemeral=True)
                log.info("Opening add-option modal")
                return await ctx.send_modal(
                    Modal(
                        "Add Option",
                        [ShortText(label="Option", custom_id="new_option")],
                        custom_id="add_option_modal|{}".format(ctx.message.id),
                    )
                )
            else:
                return await ctx.send("Cannot add options to that poll", ephemeral=True)
        elif "poll_option" in ctx.custom_id:
            await ctx.defer(ephemeral=True)

            option_index = int(ctx.custom_id.removeprefix("poll_option|"))

            if poll := await self.poll_cache.get_poll(message_id):
                if poll.expired:
                    message = await self.cache.fetch_message(ctx.channel.id, message_id)
                    await message.edit(components=poll.get_components(disable=True))
                    return await ctx.send("This poll is closing - your vote will not be counted", ephemeral=True)
                async with poll.lock:
                    if not poll.expired:
                        if poll.voting_role:
                            if poll.voting_role != ctx.guild_id and not ctx.author.has_role(poll.voting_role):
                                return await ctx.send("You do not have permission to vote in this poll", ephemeral=True)

                        opt = poll.poll_options[option_index]
                        if poll.single_vote:
                            for _o in poll.poll_options:
                                if _o != opt:
                                    if ctx.author.id in _o.voters:
                                        _o.voters.remove(ctx.author.id)
                        elif poll.max_votes is not None:
                            voted_options = poll.get_user_votes(ctx.author.id)
                            if opt not in voted_options:
                                if len(voted_options) >= poll.max_votes:
                                    log.error(
                                        f"{poll.message_id}|{ctx.author.id} tried to vote for more than the max votes allowed"
                                    )
                                    embed = Embed(
                                        "You have already voted for the maximum number of options",
                                        color=BrandColors.RED,
                                    )
                                    embed.add_field("Maximum Votes", poll.max_votes)
                                    embed.add_field(
                                        "Your Votes", ", ".join([f"`{o.emoji} {o.text}`" for o in voted_options])
                                    )
                                    embed.add_field("To remove a vote", "Vote again for the option you want to remove")
                                    return await ctx.send(embed=embed, ephemeral=True)

                        if opt.vote(ctx.author.id):
                            log.info(f"Added vote to {poll.message_id}")
                            embed = Embed("Your vote has been added", color=BrandColors.GREEN)
                            embed.add_field("Option", f"⬆️ `{opt.emoji} {opt.text}`")
                            await ctx.send(embed=embed, ephemeral=True)
                        else:
                            log.info(f"Removed vote from {poll.message_id}")
                            embed = Embed("Your vote has been removed", color=BrandColors.GREEN)
                            embed.add_field("Option", f"⬇️ `{opt.emoji} {opt.text}`")
                            await ctx.send(embed=embed, ephemeral=True)

                    self.schedule_update(poll.message_id)
            else:
                # likely a legacy or deleted poll
                log.warning(f"Could not find poll with message id {message_id}")
                await ctx.send("That poll could not be edited 😕")

    def schedule_update(self, message_id: Snowflake_Type) -> None:
        job_id = f"poll_update|{message_id}"
        if self.scheduler.get_job(job_id):
            return
        self.scheduler.add_job(
            self.update_poll,
            trigger=DateTrigger(datetime.datetime.now() + datetime.timedelta(seconds=5)),
            id=job_id,
            args=[message_id],
        )
        log.debug(f"Created job to update {message_id}")

    async def update_poll(self, message_id: Snowflake_Type) -> None:
        try:
            if poll := await self.poll_cache.get_poll(message_id):
                try:
                    if not poll.expired:
                        await self.cache.fetch_message(poll.channel_id, message_id)
                except NotFound:
                    log.warning(f"Poll {poll.message_id} not found - deleting from cache")
                    return await self.poll_cache.delete_poll(poll.message_id)
                else:
                    await asyncio.gather(poll.update_messages(self), self.poll_cache.store_poll(poll))
                    log.debug(f"Updated poll {poll.message_id}")
        except Exception as e:
            log.error(f"Error updating poll {message_id}", exc_info=e)
            return

    async def schedule_close(self, poll: PollData) -> None:
        if poll.expire_time and not poll.closed:
            try:
                self.scheduler.reschedule_job(job_id=str(poll.message_id), trigger=DateTrigger(poll.expire_time))
                log.info(f"Rescheduled poll {poll.message_id} to close at {poll.expire_time}")
            except JobLookupError:
                if poll.expire_time > datetime.datetime.now():
                    self.scheduler.add_job(
                        id=str(poll.message_id),
                        name=f"Close Poll {poll.message_id}",
                        trigger=DateTrigger(poll.expire_time),
                        func=self.close_poll,
                        args=[poll.message_id],
                    )
                    log.info(f"Scheduled poll {poll.message_id} to close at {poll.expire_time}")
                else:
                    await self.close_poll(poll.message_id)
                    log.warning(f"Poll {poll.message_id} already expired - closing immediately")

    async def close_poll(self, message_id):
        poll = await self.poll_cache.get_poll(message_id)
        tasks = []
        if poll:
            async with poll.lock:
                log.info(f"Closing poll {poll.message_id}")
                poll._expired = True
                poll.expire_time = datetime.datetime.now()

                tasks.append(poll.update_messages(self))
                tasks.append(poll.send_close_message(self))
                poll.closed = True

                tasks.append(self.poll_cache.store_poll(poll))
                tasks.append(self.send_thanks_message(poll.channel_id))
        else:
            log.warning(f"Poll {message_id} not found - cannot close")

        try:
            await asyncio.gather(*tasks)
        except NotFound:
            log.warning(f"Poll {message_id} is no longer on discord - deleting from database")
            await self.poll_cache.delete_poll(poll.message_id)
        except Exception as e:
            log.error(f"Error closing poll {message_id}", exc_info=e)

    @context_menu("stress poll", CommandTypes.MESSAGE, scopes=[985991455074050078])
    async def __stress_poll(self, ctx: ComponentContext) -> None:
        # stresses out the poll system by voting a huge amount on a poll
        # this is a stress test for the system, and should not be used in production
        poll = await self.poll_cache.get_poll(ctx.target.id)
        votes_per_cycle = 30000
        cycles = 10

        if poll:
            log.warning(f"Stressing poll {poll.message_id}")
            msg = await ctx.send("Stress testing...")

            for i in range(cycles):
                start = time.perf_counter()
                for _ in range(votes_per_cycle):
                    async with poll.lock:
                        opt = random.choice(poll.poll_options)
                        voter = random.randrange(1, 10**11)
                        if not poll.expired:
                            if poll.single_vote:
                                for _o in poll.poll_options:
                                    if _o != opt:
                                        if voter in _o.voters:
                                            _o.voters.remove(voter)
                            opt.vote(voter)
                            self.schedule_update(poll.message_id)

                end = time.perf_counter()

                await asyncio.sleep(2 - (end - start))
                await msg.edit(
                    content=f"Stress testing... {i+1}/{cycles} ({votes_per_cycle:,} votes per cycle) @ {round(votes_per_cycle / (end - start)):,} votes per second"
                )
            await msg.edit(
                content=f"Stress Completed... {i+1}/{cycles} ({votes_per_cycle:,} votes per cycle) @ {round(votes_per_cycle / (end - start)):,} votes per second"
            )

        else:
            await ctx.send("That poll could not be found")

    async def send_thanks_message(self, channel_id: Snowflake_Type) -> None:
        try:
            channel = await self.cache.fetch_channel(channel_id)
            if channel:
                guild_data = await self.poll_cache.get_guild_data(channel.guild.id)
                if guild_data is None or guild_data.thank_you_sent:
                    return
                total_polls = await self.poll_cache.db.fetchval(
                    "SELECT COUNT(*) FROM polls.poll_data WHERE guild_id = $1", channel.guild.id
                )

                if total_polls >= 3:
                    embed = Embed(title="Thanks for using Inquiry!", color=BrandColors.BLURPLE)
                    vote_command = self.interactions[0].get("vote")
                    help_command = self.interactions[0].get("help")

                    description = [
                        "I hope you've enjoyed using it so far. Please excuse this shameless plug message.",
                        "",
                        f"If you have any questions; use {self.server.mention()}",
                        f"If you have feedback; use {self.feedback.mention()}",
                        f"If you want to help the bot grow; use {vote_command.mention()}",
                        f"For help guides; use {help_command.mention()}",
                        "",
                        "Otherwise, enjoy the bot!",
                    ]

                    embed.description = "\n".join(description)
                    embed.set_footer(
                        text="This is the only time Inquiry will send a message like this",
                        icon_url=self.user.avatar.url,
                    )
                    await channel.send(embed=embed)
                    guild_data.thank_you_sent = True
                    await self.poll_cache.set_guild_data(guild_data)
                    log.info(f"Sent thanks message to {channel.guild.id}")
        except Exception as e:
            log.error("Error sending thanks message", exc_info=e)

    @listen()
    async def on_guild_remove(self, event: GuildLeft) -> None:
        if self.is_ready:
            try:
                async with self.poll_cache.db.acquire() as conn:
                    total_polls = await conn.fetchval(
                        "SELECT COUNT(*) FROM polls.poll_data WHERE guild_id = $1", event.guild.id
                    )

                    await conn.execute("DELETE FROM polls.poll_data WHERE guild_id = $1", event.guild.id)
                log.info(f"Left guild {event.guild.id} -- Deleted {total_polls} related polls from database")
            except Exception as e:
                log.error("Error deleting polls on guild leave", exc_info=e)

    @listen()
    async def on_guild_join(self, event: GuildJoin) -> None:
        guild_data = await self.poll_cache.get_guild_data(event.guild.id, create=True, store=False)
        if guild_data.blacklisted:
            # this guild is blacklisted, leave
            await event.guild.leave()
            log.warning(f"Bot was invited to blacklisted guild {event.guild.id} - leaving")


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()
    token = os.getenv("TOKEN")
    asyncio.run(Bot.run(token))
