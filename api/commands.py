

class TreeAPI:
    def __init__(self):
        self.synonym_map = {}  # Synonym mapping for words with the same meaning

    def add_synonym(self, command, synonym, canonical):
        """
        Adds a synonym to the synonym map.

        Parameters:
        - synonym: The synonym word.
        - canonical: The canonical form of the word.
        """
        self.synonym_map[tuple(command)] = {synonym: canonical}


