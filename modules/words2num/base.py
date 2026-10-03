
"""Denormalize numbers, given normalized input.
"""
from . import lang_EN_US
from . import lang_ES_US


CONVERTER_CLASSES = {
    'en': lang_EN_US.evaluate,
    'en_US': lang_EN_US.evaluate,
    'es': lang_ES_US.evaluate,
    'es_US': lang_ES_US.evaluate,
    'es_MX': lang_ES_US.evaluate,
}


def w2n(text, lang='en'):
    # try the full language first
    if lang not in CONVERTER_CLASSES:
        # then try first 2 letters
        lang = lang[:2]
    if lang not in CONVERTER_CLASSES:
        raise NotImplementedError()
    convert = CONVERTER_CLASSES[lang]
    return convert(text)
