from typing_extensions import TypedDict

from naff import Snowflake_Type


class GuildData(TypedDict):
    id: Snowflake_Type
    thank_you_sent: bool
    blacklisted: bool
    blacklisted_users: list[Snowflake_Type]
