import re

STOPWORDS = {
    # Brands
    "rhize", "rhize cannabis company", "verano", "cresco labs", "cresco", "milton", "milton remedies",
    # Product types/categories
    "live", "rosin", "cart", "cartridge", "concentrate", "flower", "vape", "battery",
    "pre", "pre-roll", "preroll", "pre-roll", "dogwalker", "edible", "tincture", "topical",
    # Extraction methods
    "indoor", "outdoor", "greenhouse", "live", "hydro", "soil",
    # Descriptors
    "indica", "hybrid", "sativa", "indica-hybrid", "sativa-hybrid",
    # Quantities/Packaging
    "pack", "pk", "7pk", "universal", "bulk", "premium", "special", "edition",
    # Other
    "cannabis", "company", "laboratories", "labs"
}

WEIGHT_PATTERN = re.compile(r"\b\d+(\.\d+)?\s?(g|gram|oz|ounce|½|⅛)\b", re.I)


def extract_candidate_internal_name(product_name: str) -> str:
    """
    Deterministically extract Internal Product Name candidate
    based on observed historical patterns.
    """
    if not product_name:
        return ""

    # 1. Handle pipe-separated format: "Product | Type | Category"
    # Split by pipe and take the first element (usually the product name)
    if "|" in product_name:
        parts = [part.strip() for part in product_name.split("|")]
        if len(parts) >= 1:
            # Use the first part as the primary candidate
            name = parts[0]
        else:
            name = product_name
    else:
        name = product_name
    
    # 2. Remove brand terms from anywhere in the name
    name = re.sub(r'\bRhize\s+Rosin\b', '', name, flags=re.I)
    name = re.sub(r'\bRhize\s+Cannabis\s+Company\b', '', name, flags=re.I)
    name = re.sub(r'\bRhize\b', '', name, flags=re.I)
    name = re.sub(r'\bVerano\b', '', name, flags=re.I)
    name = re.sub(r'\bCresco\s+Labs\b', '', name, flags=re.I)
    name = re.sub(r'\bCresco\b', '', name, flags=re.I)
    
    # 3. Clean up separators and extra spaces
    name = name.replace("|", " ")
    name = re.sub(r'\s+', ' ', name).strip()
    name = re.sub(r'^\s*-\s*', '', name)  # Remove leading hyphen
    name = re.sub(r'\s*-\s*$', '', name)  # Remove trailing hyphen
    name = re.sub(r'\s*-\s*', ' ', name)  # Replace hyphens with spaces
    name = re.sub(r'\s+', ' ', name).strip()  # Final cleanup

    # 4. Remove weights
    name = WEIGHT_PATTERN.sub("", name)

    # 5. Normalize spacing and tokenize
    tokens = [t.strip() for t in name.split() if t.strip()]

    # 6. Remove stopwords and numeric tokens
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

    # 7. Title Case canonical name
    return " ".join(filtered).title()
