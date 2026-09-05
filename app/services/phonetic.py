import phonetics
from typing import Tuple

def get_phonetic_hash(word: str) -> str:
    """
    Computes the Double Metaphone hash of a word.
    Returns the primary hash. If the library returns a tuple, we take the first element.
    """
    if not word:
        return ""

    # phonetics.dmetaphone returns a list or tuple of strings, usually [primary, secondary]
    # If the word is empty or cannot be hashed, it might return empty strings.
    result = phonetics.dmetaphone(word)
    if isinstance(result, (list, tuple)) and len(result) > 0:
        return result[0] or ""
    return str(result)

def get_phonetic_hashes(word: str) -> Tuple[str, str]:
    """
    Computes both the primary and secondary Double Metaphone codes of a word.
    Returns (primary, secondary); either may be an empty string.
    """
    if not word:
        return "", ""

    result = phonetics.dmetaphone(word)
    if isinstance(result, (list, tuple)):
        primary = result[0] if len(result) > 0 else ""
        secondary = result[1] if len(result) > 1 else ""
        return primary or "", secondary or ""
    return str(result), ""
