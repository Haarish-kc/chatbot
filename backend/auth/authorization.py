import logging

logger = logging.getLogger(__name__)

def check_permission(user: dict, resource: str, action: str) -> bool:
    """
    Implements the official Core Authorization Model:
    User ➔ Role + Department + User ID + modulePermission ➔ Resource ➔ Action ➔ Scope ➔ Permission check.
    
    OPERATIONed Actions: VIEW, CREATE, UPDATE, APPROVE, DELETE
    OPERATIONed Roles: CEO, ADMIN, MANAGER, STAFF
    
    modulePermission rules:
    - User must have "INVENTORY" or "BOTH" modulePermission to access chatbot resources.
    """
    if not user or "role" not in user:
        logger.warning(f"Authorization denied: No user details or role. Payload: {user}")
        return False
        
    role = str(user.get("role", "")).upper().strip()
    dept = str(user.get("department", "")).upper().strip()
    module_perm = str(user.get("modulePermission", "")).upper().strip()
    action = action.upper()
    resource = resource.lower().strip()

    # 1. CEO Bypass
    # CEO has full access to all resources and actions across the entire system
    if role == "CEO":
        return True

    # 2. ADMIN View Bypass
    if role == "ADMIN" and action == "VIEW":
        return True

    # 3. modulePermission Verification
    # If modulePermission is explicitly specified, enforce it (allow if INVENTORY, BOTH, ALL, or not set)
    if module_perm and module_perm not in ["INVENTORY", "BOTH", "ALL"]:
        logger.warning(f"Access Denied: User modulePermission '{module_perm}' is not authorized for INVENTORY chatbot.")
        return False

    # 3. Resource & Action Permission checks
    # --- Dashboard ---
    if resource == "dashboard":
        if action == "VIEW":
            return role in ["ADMIN", "MANAGER", "STAFF"]
        return False

    # --- Locations ---
    elif resource == "locations":
        if action in ["VIEW", "CREATE"]:
            # Allowed: Admin, All Managers, Technical OPERATION staff
            # IT Staff and other department staff are Denied.
            if role == "ADMIN":
                return True
            if role == "MANAGER":
                return True
            if role == "STAFF" and dept == "TECHNICAL OPERATION":
                return True
            return False
            
        elif action == "DELETE":
            # Only CEO is allowed (handled by CEO bypass)
            return False
            
        return False

    # --- Asset Types ---
    elif resource == "asset_types":
        if action == "CREATE":
            # All users can create asset types
            return role in ["ADMIN", "MANAGER", "STAFF"]
        elif action == "DELETE":
            return False
        return False

    # --- Station Assets ---
    elif resource == "station_assets":
        if action == "VIEW":
            # CEO, Admin, Tech OPERATION Staff, Tech OPERATION Managers, Managers from other departments
            # (Basically Admin, all Managers, and Staff in Tech OPERATION dept)
            if role == "ADMIN":
                return True
            if role == "MANAGER":
                return True
            if role == "STAFF" and dept == "TECHNICAL OPERATION":
                return True
            return False
        elif action == "DELETE":
            return False
        return False

    # --- Employee Assets ---
    elif resource == "employee_assets":
        if action == "VIEW":
            return role in ["ADMIN", "MANAGER", "STAFF"]
        elif action == "DELETE":
            return False
        return False

    # --- Purchase Requests (PR) ---
    elif resource in ["purchase_requests", "pr"]:
        if action == "CREATE":
            return True
        elif action == "VIEW":
            return True
        elif action == "QUOTE_UPLOAD":
            return role == "ADMIN"
        elif action == "APPROVE":
            return role == "MANAGER"
        elif action == "DELETE":
            return False
        return False

    # --- Purchase Orders (PO) ---
    elif resource in ["purchase_orders", "po"]:
        if action == "VIEW":
            return True
        elif action == "CREATE":
            return role == "ADMIN"
        elif action == "APPROVE":
            return role == "MANAGER"
        elif action == "DELETE":
            return False
        return False
    # --- Products ---
    elif resource == "products":
        if action == "VIEW":
            return role in ["ADMIN", "MANAGER", "STAFF"]
        elif action == "DELETE":
            return False
        return False
        
    # --- Suppliers & Supplier Categories ---
    elif resource in ["suppliers", "supplier", "supplier_categories", "supplier_category", "category", "categories"]:
        if action == "VIEW":
            return role in ["ADMIN", "MANAGER"]
        elif action in ["APPROVE", "DELETE"]:
            return False
        return False

    # --- Supplier Kart & My Cart ---
    elif resource in ["supplier_kart", "supplier_cart", "my_cart", "cart", "procurement_cart"]:
        if action in ["VIEW", "CREATE", "UPDATE", "DELETE"]:
            return role in ["ADMIN", "MANAGER", "STAFF"]
        return False

    # --- Invoices ---
    elif resource == "invoices":
        if action in ["VIEW", "CREATE"]:
            return role in ["ADMIN", "MANAGER"]
        elif action == "DELETE":
            return False
        return False

    # --- Departments ---
    elif resource == "departments":
        if action == "VIEW":
            return True
        elif action == "CREATE":
            return False
        return False
        
    # --- Users ---
    elif resource == "users":
        if action == "VIEW":
            return role in ["ADMIN", "MANAGER"]
        return False
        
    # --- Generic / Other Resources ---
    elif action == "VIEW":
        return True

    return False
