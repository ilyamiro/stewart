from __future__ import division, unicode_literals, print_function
from decimal import Decimal, localcontext
import re

from .core import NumberParseException, placevalue


VOCAB = {
    'cero': (0, 'Z'),
    'uno': (1, 'D'),
    'una': (1, 'D'),
    'un': (1, 'D'),
    'dos': (2, 'D'),
    'tres': (3, 'D'),
    'cuatro': (4, 'D'),
    'cinco': (5, 'D'),
    'seis': (6, 'D'),
    'siete': (7, 'D'),
    'ocho': (8, 'D'),
    'nueve': (9, 'D'),
    'diez': (10, 'M'),
    'once': (11, 'M'),
    'doce': (12, 'M'),
    'trece': (13, 'M'),
    'catorce': (14, 'M'),
    'quince': (15, 'M'),
    'dieciséis': (16, 'M'),
    'diecisiete': (17, 'M'),
    'dieciocho': (18, 'M'),
    'diecinueve': (19, 'M'),
    'veinte': (20, 'T'),
    'veintiuno': (21, 'T'),
    'veintidós': (22, 'T'),
    'veintitrés': (23, 'T'),
    'veinticuatro': (24, 'T'),
    'veinticinco': (25, 'T'),
    'veintiséis': (26, 'T'),
    'veintisiete': (27, 'T'),
    'veintiocho': (28, 'T'),
    'veintinueve': (29, 'T'),
    'treinta': (30, 'T'),
    'cuarenta': (40, 'T'),
    'cincuenta': (50, 'T'),
    'sesenta': (60, 'T'),
    'setenta': (70, 'T'),
    'ochenta': (80, 'T'),
    'noventa': (90, 'T'),
    'cien': (100, 'H'),
    'ciento': (100, 'H'),
    'doscientos': (200, 'H'),
    'trescientos': (300, 'H'),
    'cuatrocientos': (400, 'H'),
    'quinientos': (500, 'H'),
    'seiscientos': (600, 'H'),
    'setecientos': (700, 'H'),
    'ochocientos': (800, 'H'),
    'novecientos': (900, 'H'),
    'mil': (10**3, 'X'),
    'millón': (10**6, 'X'),
    'millones': (10**6, 'X'),
    'billón': (10**9, 'X'),
    'billones': (10**9, 'X'),
    'trillón': (10**12, 'X'),
    'trillones': (10**12, 'X'),
    'cuatrillón': (10**15, 'X'),
    'quintillón': (10**18, 'X'),
    'sextillon': (10**21, 'X'),
    'septillón': (10**24, 'X'),
    'octillón': (10**27, 'X'),
    'nonillion': (10**30, 'X'),
    'decillion': (10**33, 'X'),
    'undecillion': (10**36, 'X'),
    'duodillion': (10**39, 'X'),
    'tredecillion': (10**42, 'X'),
    'quattuordecillion': (10**45, 'X'),
    'quindecillion': (10**48, 'X'),
    'sexdecillion': (10**51, 'X'),
    'septendecillion': (10**54, 'X'),
    'octodecillón': (10**57, 'X'),
    'novemdecillion': (10**60, 'X'),
    'vigintillion': (10**63, 'X'),
    'centillón': (10**303, 'X')
}


class FST:
    def __init__(self):
        def f_zero(self, n):
            assert n == 0
            self.value = n

        def f_add(self, n):
            self.value += n

        def f_mul(self, n):
            output = self.value * n
            self.value = 0
            return output

        def f_mul_hundred(self, n):
            assert n == 100
            self.value *= n

        def f_mul_hundred_and_add(self, n):
            self.value *= 100
            self.value += n

        def f_ret(self, _):
            return self.value

        self.value = 0
        self.state = 'S'
        self.edges = {
            ('S', 'Z'): f_zero,    # 0
            ('S', 'D'): f_add,     # 9
            ('S', 'T'): f_add,     # 90
            ('S', 'M'): f_add,     # 19
            ('S', 'H'): f_add,    # 100
            ('S', 'F'): f_ret,     # 1
            ('D', 'X'): f_mul,     # 9000
            ('D', 'F'): f_ret,     # 9
            ('T', 'D'): f_add,     # 99
            ('T', 'X'): f_mul,     # 90000
            ('T', 'F'): f_ret,     # 90
            ('M', 'X'): f_mul,     # 19000
            ('M', 'F'): f_ret,     # 19
            ('H', 'D'): f_add,     # 909
            ('H', 'T'): f_add,     # 990
            ('H', 'M'): f_add,     # 919
            ('H', 'X'): f_mul,     # 900000
            ('H', 'F'): f_ret,     # 900
            ('X', 'D'): f_add,     # 9009
            ('X', 'T'): f_add,     # 9090
            ('X', 'M'): f_add,     # 9019
            ('X', 'H'): f_add,     # 9900
            ('X', 'F'): f_ret,     # 9000
            ('Z', 'F'): f_ret,     # 0
            ('S', 'X'): f_add,      # 1000
        }

    def transition(self, token):
        value, label = token
        try:
            edge_fn = self.edges[(self.state, label)]
        except KeyError:
            raise NumberParseException(f"Invalid number state from {self.state} to {label}")

        self.state = label
        return edge_fn(self, value)


def compute_placevalues(tokens):
    """Compute the placevalues for each token in the list tokens"""
    pvs = []
    for tok in tokens:
        if tok == 'punto':
            pvs.append(0)
        else:
            pvs.append(placevalue(VOCAB[tok][0]))
    return pvs

def tokenize(text):
    tokens = re.split(r"[\s,\-]+(?:y)?", text.lower())
    # Remove empty strings caused by split
    tokens = [tok for tok in tokens if tok]
    try:
        # don't use generator here because we want to raise the exception
        # here now if the word is not found in vocabulary (easier debug)
        decimal = False
        parsed_tokens = []
        decimal_tokens = []
        mul_tokens = []
        pvs = compute_placevalues(tokens)
        # Loop until all trailing multiplier tokens are removed and added to mul_tokens; Loop conditions:
        # 1: The last token in the list must have the highest placevalue of any token
        # 2: The list of tokens must be longer than one (to prevent extracting all tokens as mul_tokens)
        # 3: The maximum placevalue must be greater than 1 (This limits our mul_tokens to "hundred" or greater)
        while max(pvs) == pvs[-1] and len(pvs) > 1 and max(pvs) > 1:
            mul_tokens.insert(0, VOCAB[tokens.pop()])
            pvs.pop()

        for token in tokens:
            if token == 'punto':
                if decimal:
                    raise ValueError(f"Invalid decimal word '{token}'")
                else:
                    decimal = True
            else:
                if decimal:
                    decimal_tokens.append(VOCAB[token])
                else:
                    parsed_tokens.append(VOCAB[token])
    except KeyError as e:
        raise ValueError(f"Invalid number word: {e} in {text}")
    if decimal and not decimal_tokens:
        raise ValueError(f"Invalid sequence: no tokens following 'point'")
    return parsed_tokens, decimal_tokens, mul_tokens


def compute(tokens):
    """Compute the value of given tokens.
    """
    fst = FST()
    outputs = []
    last_placevalue = None
    for token in tokens:
        out = fst.transition(token)
        if out:
            outputs.append(out)
            if last_placevalue and last_placevalue <= placevalue(outputs[-1]):
                raise NumberParseException(f"Invalid sequence {outputs}")
            last_placevalue = placevalue(outputs[-1])
    outputs.append(fst.transition((None, 'F')))
    if last_placevalue and last_placevalue <= placevalue(outputs[-1]):
        raise NumberParseException(f"Invalid sequence {outputs}")
    return sum(outputs)


def compute_multipliers(tokens):
    """
    Determine the multiplier based on the tokens at the end of
    a number (e.g. million from "one thousand five hundred million")
    """
    total = 1
    for token in tokens:
        value, label = token
        total *= value
    return total


def compute_decimal(tokens):
    """Compute value of decimal tokens."""
    with localcontext() as ctx:
        # Locally sets decimal precision to 15 for all computations
        ctx.prec = 15
        total = Decimal()
        place = -1
        for token in tokens:
            value, label = token
            if label not in ('D', 'Z'):
                raise NumberParseException("Invalid sequence after decimal point")
            else:
                total += value * Decimal(10) ** Decimal(place)
                place -= 1
    return float(total) if tokens else 0


def evaluate(text):
    tokens, decimal_tokens, mul_tokens = tokenize(text)
    if not tokens and not decimal_tokens:
        raise ValueError(f"No valid tokens in {text}")

    return (compute(tokens) + compute_decimal(decimal_tokens)) * compute_multipliers(mul_tokens)
