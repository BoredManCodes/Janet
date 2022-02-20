from dis_snek.models import (
    Scale
)


class PermissionManagement(Scale):

    print("Do stuff")


def setup(bot):
    PermissionManagement(bot)
