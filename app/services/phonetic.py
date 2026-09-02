import phonetics

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
