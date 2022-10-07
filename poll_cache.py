import asyncio
import logging
import os
from asyncio import Event
from typing import Any

import asyncpg
import orjson
from asyncpg import Record, Pool
from naff import Snowflake_Type, Task, IntervalTrigger
from naff.client.errors import Forbidden
from naff.client.utils import TTLCache
from nafftrack.stats import BUCKETS
from prometheus_client import Gauge, Histogram

from models.elimination_poll import EliminationPoll
from models.guild_data import GuildData, GuildDataPayload
from models.poll import PollData

log = logging.getLogger("Inquiry")


class PollCache:
    def __init__(self, bot, database, credentials):
        self.bot = bot

        self.db: Pool = database
        self.credentials: dict = credentials

        self.polls: TTLCache = TTLCache(
            soft_limit=150,
            hard_limit=10000,
            ttl=1800,  # 30 minutes
            on_expire=lambda _, value: asyncio.create_task(self.__write_poll(value)),
        )
        self.guild_data: TTLCache = TTLCache(
            soft_limit=150,
            hard_limit=10000,
            ttl=1800,  # 30 minutes
            on_expire=lambda _, value: asyncio.create_task(self.set_guild_data(value)),
        )
        self.ready: Event = Event()
        self._polls_cached = Gauge("cached_polls", "How many polls are in the cache")
        self._total_polls = Gauge("total_polls", "How many polls are in the database")
        self._thanked_guilds = Gauge("thanked_guilds", "How many guilds have received a thank you message")

        task = Task.create(IntervalTrigger(seconds=30))(self._update_stats)
        task.start()

    @classmethod
    async def initialize(cls, bot):
        try:
            db_credentials = {
                "user": os.environ["POSTGRES_USER"],
                "password": os.environ["POSTGRES_PASSWORD"],
                "database": os.environ["POSTGRES_DB"],
                "host": os.environ["POSTGRES_HOST"],
            }
            database: Pool = await asyncpg.create_pool(**db_credentials)

            log.info(f"Connected to postgres as {db_credentials['user']}")
            log.debug("Writing sanity check to database")
            test_poll = PollData(
                client=bot,
                title="test",
                author_id=1234,
                channel_id=1234,
                guild_id=12345,
                message_id=1234,
                colour="blurple",
            )

            instance = cls(bot, database, db_credentials)
            await instance.__write_poll(test_poll)
            await instance.delete_poll(test_poll.message_id)

            asyncio.create_task(instance.load_all())

            return instance
        except Exception as e:
            log.critical(f"Failed to initialize cache", exc_info=e)
            exit()

    async def stop(self):
        log.info("Closing cache...")
        poll_tasks = [self.__write_poll(poll) for poll in self.polls.values()]
        guild_tasks = [self.set_guild_data(guild) for guild in self.guild_data.values()]
        await asyncio.gather(*poll_tasks, *guild_tasks)

    @staticmethod
    def assemble_query_with_dict(query: str, data: dict) -> str:
        query = query.format(
            ", ".join('"{0}"'.format(k) for k in data.keys()),
            ", ".join(f"${i + 1}" for i in range(len(data))),
            ", ".join(f'"{k}"=${i + 1}' for i, k in enumerate(data.keys())),
        )
        return query

    async def __write_poll(self, poll: PollData):
        if poll.deleted:
            return
        serialised = poll.to_dict()
        poll_query = self.assemble_query_with_dict(
            "INSERT INTO polls.poll_data ({}) VALUES ({}) ON CONFLICT(message_id) DO UPDATE SET {};", serialised
        )
        async with self.db.acquire() as conn:
            await conn.execute(poll_query, *serialised.values())

        log.debug("Wrote poll to database: %s", poll.message_id)

    @property
    def total_polls(self) -> int:
        return len(self.polls)

    @staticmethod
    def _to_optional_snowflake(value) -> int | None:
        if value == "None":
            # handle deserialization
            return None
        return int(value)

    async def load_all(self):
        if not self.bot.is_ready:
            log.debug("Waiting for client to be ready")
            await self.bot.wait_until_ready()
        log.info("Loading polls from database...")
        async with self.db.acquire() as conn:
            polls = await conn.fetch("SELECT * FROM polls.poll_data WHERE expire_time IS NOT NULL AND EXPIRED IS FALSE")

        polls = [await self.deserialize_poll(p, store=False) for p in polls]
        await asyncio.gather(*(self.bot.schedule_close(poll) for poll in polls))
        self.ready.set()

    @staticmethod
    def migrate_poll(data: dict[str, Any]) -> dict[str, Any]:
        """A placeholder method to be used for migration of data"""
        if data.get("poll_type", None) is None:
            data["poll_type"] = "default"
        return data

    async def deserialize_poll(self, data: Record, *, store: bool = True) -> PollData:
        try:
            if poll := self.polls.get(data["message_id"]):
                # prevent edge case data loss
                return poll

            data = dict(data)
            data = self.migrate_poll(data)

            data["poll_options"] = orjson.loads(data["poll_options"])
            match data["poll_type"]:
                case "elimination":
                    poll = EliminationPoll.from_dict(data, self.bot)
                case _:
                    poll = PollData.from_dict(data, self.bot)

            if not poll.author_name or not poll.author_avatar or poll.author_name == "Unknown":
                try:
                    author = await self.bot.fetch_member(poll.author_id, poll.guild_id)
                except Forbidden:
                    author = None
                if author:
                    poll.author_name = author.display_name
                    poll.author_avatar = author.avatar_url
                else:
                    poll.author_name = "Unknown"
                    poll.author_avatar = "https://cdn.discordapp.com/embed/avatars/0.png"

            if store:
                self.polls[poll.message_id] = poll
                log.debug(f"Cached poll: {poll.message_id}")
            else:
                log.debug(f"Deserialized poll: {poll.message_id}")

            return poll
        except (ValueError, KeyError, TypeError) as e:
            log.warning(f"Failed to fetch poll: {data['message_id']}", exc_info=e)

    async def __fetch_poll(self, message_id: Snowflake_Type) -> PollData | None:
        async with self.db.acquire() as conn:
            poll = await conn.fetchrow("SELECT * FROM polls.poll_data WHERE message_id = $1", int(message_id))
        if poll:
            log.debug("Fetched poll: %s", message_id)
            return await self.deserialize_poll(poll)
        return None

    async def get_poll(self, message_id: Snowflake_Type) -> PollData | None:
        if poll := self.polls.get(message_id):
            return poll
        return await self.__fetch_poll(message_id)

    async def get_polls_by_guild(self, guild_id: Snowflake_Type) -> list[PollData]:
        async with self.db.acquire() as conn:
            polls = await conn.fetch("SELECT * FROM polls.poll_data WHERE guild_id = $1", int(guild_id))
        return [await self.deserialize_poll(p, store=True) for p in polls]

    async def store_poll(self, poll: PollData) -> None:
        async with poll.lock:
            self.polls[poll.message_id] = poll
            await self.__write_poll(poll)

    async def delete_poll(self, message_id) -> None:
        lock = asyncio.Lock()  # redundant lock to prevent exceptions

        if message_id in self.polls:
            lock = self.polls[message_id].lock

        async with lock:
            async with self.db.acquire() as conn:
                await conn.execute("DELETE FROM polls.poll_data WHERE message_id = $1", int(message_id))
            poll = self.polls.pop(message_id, None)
            if poll:
                # set a deleted flag on the poll object in case another task has a reference to it
                poll.deleted = True
            log.info("Deleted poll: %s", message_id)

    async def get_total_polls(self) -> int:
        return await self.db.fetchval("SELECT COUNT(*) FROM polls.poll_data")

    async def get_guild_data(self, guild_id: Snowflake_Type, *, create: bool = False, store: bool = True) -> GuildData:
        if guild := self.guild_data.get(guild_id):
            return guild
        out = None

        async with self.db.acquire() as conn:
            data = await conn.fetchrow("SELECT * FROM polls.guild_data WHERE id = $1", int(guild_id))
            if data:
                out = GuildData.from_dict(data)
            elif create:
                await conn.execute("INSERT INTO polls.guild_data (id) VALUES ($1)", int(guild_id))
                data = await conn.fetchrow("SELECT * FROM polls.guild_data WHERE id = $1", int(guild_id))
                out = GuildData.from_dict(data)

        if store:
            self.guild_data[guild_id] = out
        return out

    async def set_guild_data(self, data: GuildData) -> None:
        payload: GuildDataPayload = data.to_dict()
        query = self.assemble_query_with_dict(
            "INSERT INTO polls.guild_data ({}) VALUES ({}) ON CONFLICT(id) DO UPDATE SET {};", payload
        )
        async with self.db.acquire() as conn:
            await conn.execute(query, *payload.values())
            log.debug("Updated guild data: %s", payload["id"])

    async def _update_stats(self):
        await self.bot.wait_until_ready()

        async with self.db.acquire() as conn:
            # print(len(self.polls))
            # print(await self.get_total_polls())
            self._polls_cached.set(len(self.polls))
            self._total_polls.set(await conn.fetchval("SELECT COUNT(*) FROM polls.poll_data"))
            self._thanked_guilds.set(
                await conn.fetchval("SELECT COUNT(*) FROM polls.guild_data WHERE thank_you_sent is true")
            )
