import json
import os

# Absolute path ensures the Worker finds it regardless of where execution starts
REGISTRY_PATH = '/Users/VedicRGI_Worker/chitta/config/user_registry.json'

def load_registry():
    if not os.path.exists(REGISTRY_PATH):
        return {}
    with open(REGISTRY_PATH, 'r') as f:
        return json.load(f)

def build_context_prompt(sender, message):
    registry = load_registry()
    
    if sender not in registry:
        return None  # BLOCKED
        
    user = registry[sender]
    role = user['role']
    tags = user.get('context_tags', [])
    
    # 1. Base Security Posture
    security_level = "HIGH"
    if role == 'ADMIN':
        security_level = "ZERO (Owner)"
    
    # 2. Tone Modulation
    tone = "Professional and concise."
    if role == 'MITRA':
        if 'casual' in tags:
            tone = "Casual, uses slang (bro/dude), authentic friend behavior."
        elif 'business_partner' in tags:
            tone = "Professional but warm. You are discussing a shared venture."
    elif role == 'GRIHASTA':
        tone = "Respectful, patient, very simple language."
    elif role == 'RISHI':
        tone = "Intellectual, academic, rigorous."

    # 3. Construct System Prompt
    system_prompt = f"""
    [INTERACTION METADATA]
    User: {user['name']}
    Role: {role}
    Tags: {', '.join(tags)}
    Security Level: {security_level}
    
    [YOUR PERSONA]
    You are Vinodh's digital extension.
    TONE INSTRUCTION: {tone}
    
    [STRICT BOUNDARIES]
    {user['system_prompt_addendum']}
    
    [GLOBAL RULES]
    - If Role is NOT 'ADMIN', do NOT execute 'openclaw' terminal commands.
    - If Role is NOT 'ADMIN', do NOT reveal location or financial specifics unless explicitly authorized in boundaries.
    """
    
    return system_prompt
