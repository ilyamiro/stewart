"""Commonly used tools
"""


class NumberParseException(Exception):
    def __init__(self, msg):
        Exception.__init__(self, msg)


def placevalue(n, base=10):
    exp = 0
    while n >= base:
        exp += 1
        n /= 10
    return exp
