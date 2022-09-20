import asyncio
import logging
import os
from asyncio import Event

import asyncpg
import orjson
from asyncpg import Record, Pool
from naff import Snowflake_Type
from naff.client.errors import Forbidden
from naff.client.utils import TTLCache

from models.poll import PollData

log = logging.getLogger("Cache")


class PollCache:
    def __init__(self, bot, database, credentials):
        self.bot = bot

        self.db: Pool = database
        self.credentials: dict = credentials

        self.polls: TTLCache = TTLCache(
            soft_limit=25,
            hard_limit=1000,
            ttl=120,
            on_expire=lambda _, value: asyncio.create_task(self.__write_poll(value)),
        )
        self.ready: Event = Event()

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
                title="test", author_id=1234, channel_id=1234, guild_id=12345, message_id=1234, colour="blurple"
            )

            instance = cls(bot, database, db_credentials)
            await instance.__write_poll(test_poll)

            asyncio.create_task(instance.load_all())

            return instance
        except Exception as e:
            log.critical(f"Failed to initialize cache", exc_info=e)
            exit()

    async def __write_poll(self, poll: PollData):
        serialised = poll.__dict__()
        poll_query = "INSERT INTO polls.poll_data ({}) VALUES ({}) ON CONFLICT(message_id) DO UPDATE SET {};".format(
            ", ".join('"{0}"'.format(k) for k in serialised.keys()),
            ", ".join(f"${i + 1}" for i in range(len(serialised))),
            ", ".join(f'"{k}"=${i + 1}' for i, k in enumerate(serialised.keys())),
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
            polls = await conn.fetch("SELECT * FROM polls.poll_data")
        polls = [await self.deserialize_poll(p, store=False) for p in polls]
        await asyncio.gather(*(self.bot.schedule_close(poll) for poll in polls))
        self.ready.set()

    async def deserialize_poll(self, data: Record, *, store: bool = True) -> PollData:
        try:
            data = dict(data)
            data["poll_options"] = orjson.loads(data["poll_options"])
            poll = PollData(**data)

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
        log.warning("Poll does not exist in database: %s", message_id)
        return None

    async def get_poll(self, message_id: Snowflake_Type) -> PollData | None:
        if poll := self.polls.get(message_id):
            log.debug("Fetched poll from cache: %s", message_id)
            return poll
        log.debug("Poll not in cache, fetching from database: %s", message_id)
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
            self.polls.pop(message_id, None)
            log.debug("Deleted poll: %s", message_id)

    async def get_total_polls(self) -> int:
        return await self.db.fetchval("SELECT COUNT(*) FROM polls.poll_data")
