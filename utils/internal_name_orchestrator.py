from utils.product_name_mapping import load_auto_mappings, save_auto_mapping
from utils.mapping_history import log_mapping_event
from utils.ai_agent import ai_extract_internal_name
import smtplib
from email.message import EmailMessage
import mail_cfg
from datetime import datetime
from typing import List, Dict, Any

AUTO_PATTERNS = load_auto_mappings()

# Global batch notification storage
_AI_MAPPINGS_BATCH = []

def add_ai_mapping_to_batch(raw_name: str, internal_name: str, confidence: float, quality_score: float = None):
    """Add AI mapping to batch notification list"""
    global _AI_MAPPINGS_BATCH
    _AI_MAPPINGS_BATCH.append({
        'raw_name': raw_name,
        'internal_name': internal_name,
        'confidence': confidence,
        'quality_score': quality_score,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

def send_batch_ai_notifications():
    """Send batch email notification for all AI-generated mappings"""
    global _AI_MAPPINGS_BATCH
    
    if not _AI_MAPPINGS_BATCH:
        return
    
    try:
        sender_email = mail_cfg.user
        receiver = mail_cfg.receiver_test  # Send to test first
        
        # Create HTML table for batch mappings
        table_rows = ""
        for mapping in _AI_MAPPINGS_BATCH:
            quality_info = f"<td>{mapping['quality_score']:.2f}</td>" if mapping['quality_score'] else "<td>-</td>"
            table_rows += f"""
            <tr>
                <td>{mapping['timestamp']}</td>
                <td>{mapping['raw_name']}</td>
                <td>{mapping['internal_name']}</td>
                <td>{mapping['confidence']:.2%}</td>
                {quality_info}
            </tr>
            """
        
        subject = f"Batch AI Product Mappings - {len(_AI_MAPPINGS_BATCH)} New Mappings"
        body = f"""
        <h2>Batch AI-Generated Product Mappings</h2>
        <p><strong>Total New Mappings:</strong> {len(_AI_MAPPINGS_BATCH)}</p>
        <p><strong>Generated:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse; width: 100%;">
            <thead>
                <tr style="background-color: #f2f2f2;">
                    <th>Timestamp</th>
                    <th>Original Product Name</th>
                    <th>Generated Internal Name</th>
                    <th>Confidence</th>
                    <th>Quality Score</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
        
        <br>
        <p>All mappings have been automatically added to PRODUCT_NAME_PATTERNS.</p>
        <p>Menu Scraping Team</p>
        """
        
        message = EmailMessage()
        message["From"] = sender_email
        message["To"] = receiver
        message["Subject"] = subject
        message.set_content(body, 'html')
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(sender_email, mail_cfg.pw)
            smtp.sendmail(sender_email, receiver, message.as_string())
        
        print(f"✓ Batch AI mapping notification sent for {len(_AI_MAPPINGS_BATCH)} mappings")
        
        # Clear the batch after sending
        _AI_MAPPINGS_BATCH.clear()
        
    except Exception as e:
        print(f"✗ Failed to send batch AI mapping notification: {e}")

def send_ai_mapping_notification(raw_name: str, internal_name: str, confidence: float):
    """Legacy function - now adds to batch instead of sending immediately"""
    add_ai_mapping_to_batch(raw_name, internal_name, confidence)


def ensure_internal_product_name(product: dict) -> dict:
    """
    AI-ONLY canonical name extractor.

    GUARANTEES:
    - AI runs ONLY if Internal Product Name is missing
    - Existing mappings are NEVER modified
    - New mappings are append-only
    - NO rule-based fallback - AI only
    """

    raw_name = product.get("Product name", "")
    existing_name = product.get("Internal Product Name", "").strip()

    # 🔒 HARD STOP: never touch existing data
    if existing_name:
        return product

    # 🤖 AI AGENT CALL - ONLY AI, NO FALLBACK
    ai_result = ai_extract_internal_name(raw_name)

    if not ai_result:
        # AI declined - return product without any internal name
        return product

    name = ai_result["internal_product_name"]
    confidence = ai_result["confidence"]
    quality_score = ai_result.get("quality_score")
    key = name.lower()

    # 🔒 HARD STOP: never overwrite existing mappings
    if key in AUTO_PATTERNS:
        product["Internal Product Name"] = AUTO_PATTERNS[key]
        return product

    # ✅ Append new AI mapping
    save_auto_mapping(key, name)
    log_mapping_event(
        raw_product_name=raw_name,
        normalized_key=key,
        internal_name=name,
        confidence=confidence,
        source="ai_agent"
    )

    AUTO_PATTERNS[key] = name
    product["Internal Product Name"] = name
    
    # 📧 Add to batch notification for new AI mapping
    add_ai_mapping_to_batch(raw_name, name, confidence, quality_score)

    return product
