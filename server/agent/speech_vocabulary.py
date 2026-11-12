"""Bounded game-owned vocabulary, read only while the game link is active."""
import unicodedata

MAX_TERMS = 64
MAX_TERM_CHARS = 24
MAX_CHARS = 512


def terms(value):
    if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != 1 or value.get('language') != 'ja':
        return ()
    values = value.get('terms')
    if not isinstance(values, list) or len(values) > MAX_TERMS:
        return ()
    result = []
    for word in values:
        if not isinstance(word, str) or not word or word != word.strip() or len(word) > MAX_TERM_CHARS:
            return ()
        if any(unicodedata.category(c).startswith('C') for c in word):
            return ()
        if word not in result:
            result.append(word)
    if sum(map(len, result)) > MAX_CHARS:
        return ()
    return tuple(result)


def game_terms(game):
    if game is None or not game.linked:
        return ()
    return terms(game.profile.get('speech_vocabulary'))
