import hashlib
import os
import json
from datetime import datetime


def generate_user_id(first_name, last_name):
    """
    Generate a consistent user ID from first and last name.
    This ensures the same ID is generated for the same user across sessions.
    
    Args:
        first_name (str): User's first name
        last_name (str): User's last name
        
    Returns:
        str: A consistent user ID
    """
    # Normalize inputs to handle inconsistent casing/spacing
    first = first_name.strip().lower()
    last = last_name.strip().lower()
    
    # Create a unique identifier
    combined = f"{first}_{last}_{datetime.now().strftime('%Y%m')}"
    
    # Create a hash to use as ID
    hashed = hashlib.md5(combined.encode()).hexdigest()
    
    # Return a portion of the hash as the user ID
    return f"user_{hashed[:10]}"


def load_support_knowledge_base():
    """
    Load the customer support knowledge base from a JSON file.
    If file doesn't exist, return a default knowledge base.
    
    Returns:
        str: Formatted knowledge base content
    """
    kb_file = os.path.join(os.path.dirname(__file__), "support_kb.json")
    
    try:
        if os.path.exists(kb_file):
            with open(kb_file, "r") as f:
                kb_data = json.load(f)
                
            # Format knowledge base into readable text
            kb_text = "# KNOWLEDGE BASE ARTICLES\n\n"
            
            for article in kb_data.get("articles", []):
                kb_text += f"## {article.get('title', 'Untitled Article')}\n"
                kb_text += f"ID: {article.get('id', 'unknown')}\n"
                kb_text += f"{article.get('content', 'No content available')}\n\n"
                
                if article.get("solutions"):
                    kb_text += "### Solutions:\n"
                    for i, solution in enumerate(article["solutions"], 1):
                        kb_text += f"{i}. {solution}\n"
                    kb_text += "\n"
                    
            return kb_text
        else:
            # Return default knowledge base if file doesn't exist
            return create_default_knowledge_base()
    except Exception as e:
        print(f"Error loading knowledge base: {e}")
        return create_default_knowledge_base()


def create_default_knowledge_base():
    """
    Create a default knowledge base with basic support information.
    
    Returns:
        str: Formatted default knowledge base
    """
    default_kb = """
# DEFAULT SUPPORT KNOWLEDGE BASE

## Account Issues
ID: KB001
Common account issues include login problems, password resets, and account verification.

### Solutions:
1. For login issues, clear browser cache and cookies first
2. Use the "Forgot Password" option on the login screen to reset password
3. Check email for verification links if account is pending verification
4. Contact support if account is locked after multiple failed login attempts

## Billing Questions
ID: KB002
Information about billing cycles, payment methods, and subscription management.

### Solutions:
1. Billing occurs on the monthly anniversary of signup date
2. Supported payment methods: credit/debit cards, PayPal, and bank transfers
3. To cancel subscription, go to Account Settings > Subscription > Cancel
4. Refunds are processed within 5-7 business days

## Technical Support
ID: KB003
Common technical issues and troubleshooting steps.

### Solutions:
1. Restart the application or refresh the browser
2. Ensure you're using a supported browser (Chrome, Firefox, Safari, Edge)
3. Check internet connection and firewall settings
4. Clear application cache in Settings > Advanced > Clear Cache

## Feature Requests
ID: KB004
Guidelines for submitting and tracking feature requests.

### Solutions:
1. Submit feature requests through the Feedback form in the Help menu
2. Include detailed description and use case for the feature
3. Vote on existing feature requests in the community portal
4. Feature request status updates are sent via email when available
"""
    return default_kb


def format_conversation_history(messages):
    """
    Format conversation history into a readable markdown format.
    
    Args:
        messages (list): List of message dictionaries with 'role' and 'content'
        
    Returns:
        str: Formatted conversation history
    """
    if not messages:
        return "No conversation history available."
        
    formatted = "# Conversation History\n\n"
    
    for i, msg in enumerate(messages, 1):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        
        if role == "user":
            formatted += f"**User**: {content}\n\n"
        elif role == "assistant":
            formatted += f"**Assistant**: {content}\n\n"
        else:
            formatted += f"**{role.capitalize()}**: {content}\n\n"
            
    return formatted


def extract_ticket_info(session):
    """
    Extract ticket information from a session object.
    
    Args:
        session: Zep session object
        
    Returns:
        dict: Ticket information
    """
    if not session or not session.metadata:
        return {
            "ticket_id": "Unknown",
            "status": "unknown",
            "created_at": "Unknown",
            "issue_title": "Unknown Issue"
        }
        
    metadata = session.metadata
    
    return {
        "ticket_id": metadata.get("ticket_id", "Unknown"),
        "status": metadata.get("status", "unknown"),
        "created_at": metadata.get("created_at", "Unknown"),
        "issue_title": metadata.get("issue_title", "Unknown Issue"),
        "last_updated": metadata.get("updated_at", metadata.get("created_at", "Unknown"))
    }