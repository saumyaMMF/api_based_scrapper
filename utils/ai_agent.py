import json
import os
import re
from typing import Dict, Any
from utils.name_validation import validate_generated_name

def call_llm(prompt: str) -> Dict[str, Any]:
    """
    Call Claude Code API for internal name extraction.
    """
    try:
        # You'll need to set up your Claude API key
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            print("Warning: ANTHROPIC_API_KEY not found, using fallback")
            return {"internal_product_name": None, "confidence": 0}
        
        # Claude API call implementation
        import anthropic
        
        client = anthropic.Anthropic(api_key=api_key)
        
        try:
            response = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=100,
                temperature=0.1,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            # Parse the response
            content = response.content[0].text.strip()
            
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{.*?\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return result
            else:
                # Fallback: try to parse entire response as JSON
                return json.loads(content)
                
        except Exception as api_error:
            print(f"Claude API error: {api_error}")
            return {"internal_product_name": None, "confidence": 0}
        
    except Exception as e:
        print(f"AI API call failed: {e}")
        return {"internal_product_name": None, "confidence": 0}

def ai_extract_internal_name(product_name: str) -> dict | None:
    """
    AI agent that ONLY extracts canonical internal product names.
    No memory, no autonomy, no retries.
    Enhanced with comprehensive quality validation.
    """

    prompt = f"""
You are a canonical product naming assistant for a cannabis inventory system.

Task:
Extract the canonical Internal Product Name.

Rules:
- Remove brand names
- Remove weights and units
- Remove product formats (rosin, cart, preroll, flower, battery, etc.)
- Do NOT invent new words
- Do NOT include brand names
- Title Case output
- If uncertain, return null

Product name:
"{product_name}"

Return JSON ONLY:
{{
  "internal_product_name": string | null,
  "confidence": number between 0 and 1
}}
"""

    response = call_llm(prompt)  # Claude Code API / OpenAI

    name = response.get("internal_product_name")
    confidence = response.get("confidence", 0)

    # 🔒 Basic validation gate
    if not name:
        print(f"AI: No name generated for '{product_name}'")
        return None
    if confidence < 0.85:
        print(f"AI: Low confidence ({confidence:.2f}) for '{name}' from '{product_name}'")
        return None
    if len(name.strip()) < 3:
        print(f"AI: Name too short '{name}' from '{product_name}'")
        return None

    # 🔍 Enhanced quality validation
    validation_result = validate_generated_name(name.strip(), confidence)
    
    if not validation_result['is_valid']:
        print(f"AI: Name '{name}' rejected - {validation_result['recommendation']}")
        if validation_result['issues']:
            print(f"   Issues: {', '.join(validation_result['issues'])}")
        return None
    
    # Use adjusted confidence that accounts for quality
    final_confidence = validation_result['adjusted_confidence']
    
    print(f"AI: Accepted '{name}' with quality score {validation_result['quality_score']:.2f} "
          f"and adjusted confidence {final_confidence:.2f}")

    return {
        "internal_product_name": name.strip(),
        "confidence": final_confidence,
        "quality_score": validation_result['quality_score'],
        "validation_issues": validation_result['issues']
    }
