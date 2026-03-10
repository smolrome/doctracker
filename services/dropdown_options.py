"""
services/dropdown_options.py — Service for managing customizable dropdown options.
"""
import json

from services.database import USE_DB, get_conn


# Default options when no custom options are defined
DEFAULT_CATEGORY_OPTIONS = [
    "Letter", "Memorandum", "Report", "Application", "Voucher",
    "Plantilla", "Payroll", "Memo", "Request", "Endorsement",
    "Order", "Notice", "Circular", "Certificate", "Other"
]

DEFAULT_STATUS_OPTIONS = [
    "Pending", "Received", "In Review", "In Transit", "Released", "On Hold", "Archived"
]

# Fields that can have customizable dropdowns
MANAGEABLE_FIELDS = {
    "category": "Document Type",
    "status": "Status",
    "sender_org": "Sender Office/Unit",
    "referred_to": "Referred To",
}


def _load_dropdown_options_from_db(field_name: str) -> list | None:
    """Load custom options for a field from database."""
    if not USE_DB:
        return None
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT options FROM dropdown_options WHERE field_name = %s",
                    (field_name,)
                )
                row = cur.fetchone()
                if row and row["options"]:
                    return row["options"]
    except Exception as e:
        print(f"Error loading dropdown options for {field_name}: {e}")
    return None


def _save_dropdown_options_to_db(field_name: str, options: list) -> bool:
    """Save custom options for a field to database."""
    if not USE_DB:
        return False
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO dropdown_options (field_name, options, updated_at)
                    VALUES (%s, %s::jsonb, NOW())
                    ON CONFLICT (field_name) DO UPDATE SET 
                        options = EXCLUDED.options,
                        updated_at = NOW()
                """, (field_name, json.dumps(options)))
            conn.commit()
        return True
    except Exception as e:
        print(f"Error saving dropdown options for {field_name}: {e}")
        return False


def get_dropdown_options(field_name: str) -> list:
    """
    Get dropdown options for a field.
    Returns custom options if defined, otherwise returns defaults.
    """
    # Check for custom options in database
    custom_options = _load_dropdown_options_from_db(field_name)
    if custom_options is not None:
        return custom_options
    
    # Return default options based on field name
    if field_name == "category":
        return DEFAULT_CATEGORY_OPTIONS
    elif field_name == "status":
        return DEFAULT_STATUS_OPTIONS
    else:
        return []


def get_all_dropdown_configs() -> dict:
    """Get all dropdown field configurations."""
    if not USE_DB:
        # Return defaults for JSON fallback
        return {
            "category": {
                "field_name": "category",
                "display_name": "Document Type",
                "options": DEFAULT_CATEGORY_OPTIONS,
                "is_default": True
            },
            "status": {
                "field_name": "status",
                "display_name": "Status",
                "options": DEFAULT_STATUS_OPTIONS,
                "is_default": True
            }
        }
    
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT field_name, options FROM dropdown_options ORDER BY field_name")
                rows = cur.fetchall()
        
        configs = {}
        for row in rows:
            field_name = row["field_name"]
            configs[field_name] = {
                "field_name": field_name,
                "display_name": MANAGEABLE_FIELDS.get(field_name, field_name.title()),
                "options": row["options"] if row["options"] else [],
                "is_default": False
            }
        
        # Add defaults for fields that don't have custom configs
        for field_name, display_name in MANAGEABLE_FIELDS.items():
            if field_name not in configs:
                default_options = DEFAULT_CATEGORY_OPTIONS if field_name == "category" else (
                    DEFAULT_STATUS_OPTIONS if field_name == "status" else []
                )
                configs[field_name] = {
                    "field_name": field_name,
                    "display_name": display_name,
                    "options": default_options,
                    "is_default": True
                }
        
        return configs
    except Exception as e:
        print(f"Error getting all dropdown configs: {e}")
        return {}


def update_dropdown_options(field_name: str, options: list) -> tuple[bool, str]:
    """Update dropdown options for a field. Returns (success, message)."""
    if not options:
        return False, "Options cannot be empty."
    
    # Clean up options - remove empty strings and duplicates while preserving order
    cleaned_options = []
    seen = set()
    for opt in options:
        opt = opt.strip()
        if opt and opt not in seen:
            cleaned_options.append(opt)
            seen.add(opt)
    
    if not cleaned_options:
        return False, "All options were empty after cleaning."
    
    # Validate field_name
    if field_name not in MANAGEABLE_FIELDS:
        return False, f"Invalid field name. Valid fields: {', '.join(MANAGEABLE_FIELDS.keys())}"
    
    success = _save_dropdown_options_to_db(field_name, cleaned_options)
    if success:
        return True, f"Successfully updated {MANAGEABLE_FIELDS[field_name]} options."
    else:
        return False, "Failed to save options to database."


def reset_to_default(field_name: str) -> tuple[bool, str]:
    """Reset a field's dropdown options to default."""
    if field_name == "category":
        default_options = DEFAULT_CATEGORY_OPTIONS
    elif field_name == "status":
        default_options = DEFAULT_STATUS_OPTIONS
    else:
        return False, "This field does not have default options."
    
    success = _save_dropdown_options_to_db(field_name, default_options)
    if success:
        return True, f"Successfully reset {MANAGEABLE_FIELDS[field_name]} to default options."
    else:
        return False, "Failed to reset options."
