import logging
import typing
from api import tree

log = logging.getLogger("tree")


class Tree:
    """
    Represents a trie structure for storing and retrieving voice assistant commands.
    """

    def __init__(self):
        self.api = tree

