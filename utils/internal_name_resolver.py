import re

STOPWORDS = {
    "rhize", "live", "rosin", "cart", "cartridge", "concentrate",
    "pre", "pre-roll", "preroll", "pre-roll", "flower", "dogwalker",
    "pack", "pk", "7pk", "universal"
}

WEIGHT_PATTERN = re.compile(r"\b\d+(\.\d+)?\s?(g|gram|oz|ounce|½|⅛)\b", re.I)


def extract_candidate_internal_name(product_name: str) -> str:
    """
    Deterministically extract Internal Product Name candidate
    based on observed historical patterns.
    """
    if not product_name:
        return ""

    # 1. Remove brand suffix/prefix
    name = product_name.replace("|", "-")
    
    # Remove "Rhize" and related brand terms from anywhere in the name
    name = re.sub(r'\bRhize\s+Rosin\b', '', name, flags=re.I)
    name = re.sub(r'\bRhize\b', '', name, flags=re.I)
    
    # Clean up extra spaces and hyphens
    name = re.sub(r'\s+', ' ', name).strip()
    name = re.sub(r'^\s*-\s*', '', name)  # Remove leading hyphen
    name = re.sub(r'\s*-\s*$', '', name)  # Remove trailing hyphen
    name = re.sub(r'\s*-\s*', ' ', name)  # Replace hyphens with spaces
    name = re.sub(r'\s+', ' ', name).strip()  # Final cleanup

    # 2. Remove weights
    name = WEIGHT_PATTERN.sub("", name)

    # 3. Normalize spacing
    tokens = [t.strip() for t in name.split() if t.strip()]

    # 4. Remove stopwords and numeric tokens
    filtered = []
    for i, t in enumerate(tokens):
        should_keep = (
            t.lower() not in STOPWORDS and 
            not 'walker' in t.lower() and  # Handle dogwalkers -> dogwalker
            not t.lower().endswith('pk') and  # Handle 7pk -> pk
            not (t.lower() == 'roll' and any('pre' in token.lower() for token in tokens)) and
            not t.isdigit()
        )
        
        # Filter multipack if it's not the only meaningful token
        if t.lower() == 'multipack':
            # Check if there are other non-numeric, non-stopword tokens
            other_meaningful_tokens = [
                token for j, token in enumerate(tokens) 
                if j != i and 
                token.lower() not in STOPWORDS and 
                not 'walker' in token.lower() and
                not token.lower().endswith('pk') and
                not token.isdigit()
            ]
            should_keep = len(other_meaningful_tokens) == 0
        
        if should_keep:
            filtered.append(t)

    if not filtered:
        return ""

    # 5. Title Case canonical name
    return " ".join(filtered).title()
