import re
from typing import Dict, List, Set, Tuple, Optional
from utils.product_name_mapping import load_auto_mappings

# Common cannabis brand names to filter out
KNOWN_BRANDS = {
    'rhize', 'kiva', 'canopy', 'curaleaf', 'trulieve', 'green thumb', 'gti',
    'credo', 'verano', 'moxie', 'satori', 'cresco', 'ayr', 'beacon', 'flora',
    'columbia care', 'carma', 'rythm', 'moxie', 'satori', 'cresco', 'ayr',
    'beacon', 'flora', 'columbia care', 'carma', 'rythm', 'moxie', 'satori',
    'cresco', 'ayr', 'beacon', 'flora', 'columbia care', 'carma', 'rythm',
    'vireo', 'mpx', 'surterra', 'medmen', 'apothecarium', 'harborside',
    'baklava', 'bloom', 'dosist', 'select', 'heavy hitters', 'stiiizy',
    'raw garden', 'kiva', 'canopy', 'curaleaf', 'trulieve', 'green thumb'
}

# Product type terms that should not be in internal names
PRODUCT_TYPES = {
    'cartridge', 'cart', 'vape', 'pen', 'battery', 'disposable', 'pod',
    'flower', 'bud', 'pre-roll', 'preroll', 'joint', 'blunt', 'infused',
    'concentrate', 'shatter', 'wax', 'budder', 'live resin', 'rosin',
    'sap', 'crumble', 'distillate', 'oil', 'tincture', 'edible', 'gummy',
    'chocolate', 'cookie', 'brownie', 'beverage', 'drink', 'capsule',
    'topical', 'cream', 'balm', 'lotion', 'salve', 'patch', 'spray'
}

# Quality indicators for good internal names
QUALITY_INDICATORS = {
    'strain_indicators': {
        'kush', 'haze', 'dream', 'cookies', 'punch', 'berry', 'lemon',
        'orange', 'grape', 'apple', 'pine', 'diesel', 'skunk', 'cheese',
        'sour', 'sweet', 'blue', 'purple', 'green', 'white', 'black',
        'gold', 'silver', 'platinum', 'diamond', 'fire', 'ice', 'frost'
    },
    'genetic_indicators': {
        'og', 'afghani', 'indica', 'sativa', 'hybrid', 'cross', 'genetics',
        'heritage', 'selection', 'phenotype', 'cut', 'clone', 'seed'
    }
}

def load_existing_patterns() -> Set[str]:
    """Load all existing internal product name patterns"""
    mappings = load_auto_mappings()
    return set(mappings.values())

def is_brand_name(name: str) -> bool:
    """Check if name contains known brand terms"""
    name_lower = name.lower()
    return any(brand in name_lower for brand in KNOWN_BRANDS)

def contains_product_type(name: str) -> bool:
    """Check if name contains product type terms"""
    name_lower = name.lower()
    return any(ptype in name_lower for ptype in PRODUCT_TYPES)

def has_quality_indicators(name: str) -> Tuple[bool, float]:
    """Check if name has quality strain/genetic indicators"""
    name_lower = name.lower()
    score = 0.0
    
    # Check strain indicators
    strain_matches = sum(1 for indicator in QUALITY_INDICATORS['strain_indicators'] 
                        if indicator in name_lower)
    
    # Check genetic indicators  
    genetic_matches = sum(1 for indicator in QUALITY_INDICATORS['genetic_indicators']
                         if indicator in name_lower)
    
    # Score based on matches
    score += strain_matches * 0.3
    score += genetic_matches * 0.2
    
    # Bonus for proper title case
    if name.istitle():
        score += 0.1
    
    # Bonus for reasonable length (3-4 words is ideal)
    word_count = len(name.split())
    if 2 <= word_count <= 4:
        score += 0.2
    elif word_count == 1:
        score -= 0.1
    
    return score > 0.1, min(score, 1.0)

def is_duplicate(name: str, existing_patterns: Set[str]) -> bool:
    """Check if name already exists in patterns"""
    name_normalized = name.lower().strip()
    return any(
        name_normalized == existing.lower().strip() 
        for existing in existing_patterns
    )

def calculate_quality_score(name: str, existing_patterns: Set[str]) -> Dict[str, float]:
    """Calculate comprehensive quality score for generated name"""
    scores = {
        'brand_penalty': 0.0,
        'product_type_penalty': 0.0,
        'quality_bonus': 0.0,
        'length_penalty': 0.0,
        'format_penalty': 0.0,
        'duplicate_penalty': 0.0
    }
    
    # Brand name penalty (heavy)
    if is_brand_name(name):
        scores['brand_penalty'] = -0.8
    
    # Product type penalty (medium)
    if contains_product_type(name):
        scores['product_type_penalty'] = -0.5
    
    # Quality bonus
    has_quality, quality_score = has_quality_indicators(name)
    if has_quality:
        scores['quality_bonus'] = quality_score
    
    # Length penalty
    word_count = len(name.split())
    if word_count == 1:
        scores['length_penalty'] = -0.2
    elif word_count > 5:
        scores['length_penalty'] = -0.3
    
    # Format penalty
    if not name.istitle():
        scores['format_penalty'] = -0.1
    
    # Duplicate penalty (very heavy)
    if is_duplicate(name, existing_patterns):
        scores['duplicate_penalty'] = -1.0
    
    # Calculate total score
    total_score = sum(scores.values())
    total_score = max(0.0, min(1.0, total_score + 0.5))  # Normalize to 0-1
    
    return {
        'total_score': total_score,
        'breakdown': scores,
        'recommendation': get_recommendation(total_score, scores)
    }

def get_recommendation(score: float, breakdown: Dict[str, float]) -> str:
    """Get recommendation based on score breakdown"""
    if breakdown['duplicate_penalty'] < 0:
        return "REJECT: Duplicate of existing pattern"
    if breakdown['brand_penalty'] < -0.5:
        return "REJECT: Contains brand name"
    if score < 0.3:
        return "REJECT: Low quality score"
    if score < 0.5:
        return "REVIEW: Borderline quality"
    if score < 0.7:
        return "ACCEPT: Good quality"
    return "ACCEPT: High quality"

def validate_generated_name(name: str, confidence: float, existing_patterns: Set[str] = None) -> Dict:
    """
    Comprehensive validation for AI-generated internal product names
    
    Returns:
        {
            'is_valid': bool,
            'quality_score': float (0-1),
            'recommendation': str,
            'issues': List[str],
            'adjusted_confidence': float
        }
    """
    if existing_patterns is None:
        existing_patterns = load_existing_patterns()
    
    # Basic validation
    if not name or len(name.strip()) < 3:
        return {
            'is_valid': False,
            'quality_score': 0.0,
            'recommendation': 'REJECT: Name too short',
            'issues': ['Name too short'],
            'adjusted_confidence': 0.0
        }
    
    name = name.strip()
    
    # Calculate quality score
    quality_result = calculate_quality_score(name, existing_patterns)
    
    # Collect issues
    issues = []
    if is_brand_name(name):
        issues.append('Contains brand name')
    if contains_product_type(name):
        issues.append('Contains product type')
    if is_duplicate(name, existing_patterns):
        issues.append('Duplicate of existing pattern')
    if not name.istitle():
        issues.append('Not in title case')
    
    # Determine validity
    is_valid = (
        quality_result['total_score'] >= 0.3 and
        quality_result['recommendation'].startswith('ACCEPT') and
        len(issues) == 0
    )
    
    # Adjust confidence based on quality
    adjusted_confidence = confidence * quality_result['total_score']
    
    return {
        'is_valid': is_valid,
        'quality_score': quality_result['total_score'],
        'recommendation': quality_result['recommendation'],
        'issues': issues,
        'adjusted_confidence': adjusted_confidence,
        'quality_breakdown': quality_result['breakdown']
    }
