from utils.product_name_mapping import load_auto_mappings, save_auto_mapping
from utils.mapping_history import log_mapping_event
from utils.ai_agent import ai_extract_internal_name
import smtplib
from email.message import EmailMessage
import mail_cfg

AUTO_PATTERNS = load_auto_mappings()


def send_ai_mapping_notification(raw_name: str, internal_name: str, confidence: float):
    """Send email notification for new AI-generated mapping"""
    try:
        sender_email = mail_cfg.user
        receiver = mail_cfg.receiver_test  # Send to test first
        
        subject = "New AI Product Mapping Created"
        body = f"""
        <h2>New AI-Generated Product Mapping</h2>
        <p><strong>Original Product Name:</strong> {raw_name}</p>
        <p><strong>Generated Internal Name:</strong> {internal_name}</p>
        <p><strong>Confidence:</strong> {confidence:.2%}</p>
        <p><strong>Source:</strong> AI Agent</p>
        <br>
        <p>This mapping has been automatically added to PRODUCT_NAME_PATTERNS.</p>
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
        
        print(f"✓ AI mapping notification sent for: {internal_name}")
        
    except Exception as e:
        print(f"✗ Failed to send AI mapping notification: {e}")


def ensure_internal_product_name(product: dict) -> dict:
    """
    AI-ONLY canonical name extractor.

    GUARANTEES:
    - AI runs ONLY if Internal Product Name is missing
    - Existing mappings are NEVER modified
    - New mappings are append-only
    """

    raw_name = product.get("Product name", "")
    existing_name = product.get("Internal Product Name", "").strip()

    # 🔒 HARD STOP: never touch existing data
    if existing_name:
        return product

    # 🤖 AI AGENT CALL
    ai_result = ai_extract_internal_name(raw_name)

    if not ai_result:
        return product  # AI declined / unsure

    name = ai_result["internal_product_name"]
    confidence = ai_result["confidence"]
    key = name.lower()

    # 🔒 HARD STOP: never overwrite existing mappings
    if key in AUTO_PATTERNS:
        product["Internal Product Name"] = AUTO_PATTERNS[key]
        return product

    # ✅ Append new mapping
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
    
    # 📧 Send email notification for new AI mapping
    send_ai_mapping_notification(raw_name, name, confidence)

    return product
