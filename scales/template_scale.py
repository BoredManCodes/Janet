from dis_snek.models import (
    Scale
)


class Template(Scale):

    print("Do stuff")


def setup(bot):
    Template(bot)
