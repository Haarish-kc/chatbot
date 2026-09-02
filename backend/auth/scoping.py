import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

def prune_upcoming_approvals(pr: dict) -> dict:
    """
    Prunes the approvals chain in memory so that if any level is currently pending,
    subsequent levels are not included in the payload.
    """
    approvals = pr.get("approvals", []) or []
    if not approvals:
        return pr
        
    pruned_approvals = []
    
    # Sort approvals by level (just in case they are not in order)
    try:
        sorted_approvals = sorted(approvals, key=lambda a: a.get("approvalLevel", 1))
    except Exception:
        sorted_approvals = approvals
        
    for app in sorted_approvals:
        if not isinstance(app, dict):
            continue
        pruned_approvals.append(app)
        status = str(app.get("status", "")).upper().strip()
        if status in ["PENDING", "AWAITING", "SUBMITTED"]:
            # Found the active pending level! Stop adding upcoming levels.
            break
            
    pr_copy = pr.copy()
    pr_copy["approvals"] = pruned_approvals
    return pr_copy

def filter_purchase_requests(user: dict, pr_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    TEMPORARY LIMITATION: This function performs in-memory filtering of Purchase Requests.
    If the Inventory backend adds support for API-level query parameters (e.g., ?department=X),
    this filtering should be moved to the database query level to improve performance and scalability.
    
    Real Data structure mapping from /procurement/purchase-requests:
    - Creator ID: `requestedBy` or `requester.id`
    - Creator Department: `department` or `requester.department`
    - Approver ID: `approverId` or `approver.id` inside `approvals` array
    
    PR Visibility Rules:
    - CEO, Admin, and Accounts Managers: Can view all PRs.
    - Department Managers: Can view own PRs, PRs from staff in their department, and PRs they approved/in their approval chain.
    - Staff: Can only view PRs they created (where requestedBy matches their user_id).
    """
    if not pr_data or not pr_data.get("success"):
        return pr_data

    pr_list: List[Dict[str, Any]] = pr_data.get("data", {}).get("purchaseRequests", [])
    if not pr_list:
        return pr_data

    role = str(user.get("role", "")).upper().strip()
    user_dept = str(user.get("department", "")).upper().strip()
    user_id = user.get("user_id")

    # Accounts Manager check: user is MANAGER and department is Accounts
    is_accounts_manager = (role == "MANAGER" and user_dept == "ACCOUNTS")

    # 1. Full Access: CEO, Admin, Accounts Manager
    if role in ["CEO", "ADMIN"] or is_accounts_manager:
        if settings_allow_debug():
            logger.debug(f"User {user.get('username')} granted full access to PRs.")
        pruned_list = [prune_upcoming_approvals(pr) for pr in pr_list]
        res = pr_data.copy()
        res["data"] = pr_data.get("data", {}).copy()
        res["data"]["purchaseRequests"] = pruned_list
        return res

    filtered_list = []

    # 2. Manager Access (Own department PRs, own PRs, or PRs in their approval chain)
    if role == "MANAGER":
        for pr in pr_list:
            # Check creator details
            requester = pr.get("requester", {})
            requester_id = pr.get("requestedBy") or (requester.get("id") if isinstance(requester, dict) else None)
            
            # Resolve requester department from the PR department field
            pr_dept = str(pr.get("department", "")).upper().strip()
            if not pr_dept and isinstance(requester, dict):
                pr_dept = str(requester.get("department", "")).upper().strip()

            # A. Check department match
            is_same_dept = (pr_dept == user_dept and user_dept != "")
            
            # B. Check owner match
            is_owner = (requester_id == user_id)
            
            # C. Check approval chain (is the manager listed as an approver in the approvals array)
            approvals = pr.get("approvals", []) or []
            is_in_approval_chain = False
            for app in approvals:
                if isinstance(app, dict):
                    app_id = app.get("approverId") or app.get("approver", {}).get("id")
                    if app_id == user_id:
                        is_in_approval_chain = True
                        break

            if is_same_dept or is_owner or is_in_approval_chain:
                filtered_list.append(pr)

    # 3. Staff Access (Only own PRs)
    elif role == "STAFF":
        for pr in pr_list:
            requester = pr.get("requester", {})
            requester_id = pr.get("requestedBy") or (requester.get("id") if isinstance(requester, dict) else None)
            
            if requester_id is not None and user_id is not None and str(requester_id).strip() == str(user_id).strip():
                filtered_list.append(pr)
                
    # Prune upcoming approvals for filtered list
    pruned_list = [prune_upcoming_approvals(pr) for pr in filtered_list]
    
    # Update the data list in-place and return
    res = pr_data.copy()
    res["data"] = pr_data.get("data", {}).copy()
    res["data"]["purchaseRequests"] = pruned_list
    return res


def filter_dashboard_data(user: dict, dashboard_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Filters and scopes dashboard overview KPIs based on the authenticated user's role:
    - CEO and Admin: Access to all global inventory data.
    - Managers: Access to their department's inventory data and staff inventory records.
    - Staff: Access to their own analytics only.
    """
    if not dashboard_data or not dashboard_data.get("success"):
        return dashboard_data

    role = str(user.get("role", "")).upper().strip()
    if role in ["CEO", "ADMIN"]:
        res = dashboard_data.copy()
        if "data" in res and isinstance(res["data"], dict):
            res["data"] = res["data"].copy()
            res["data"]["scope"] = "GLOBAL"
        return res

    dept = str(user.get("department", "")).strip() or "General"
    kpis = dashboard_data.get("data", {}).get("kpis", {}) if isinstance(dashboard_data.get("data"), dict) else {}

    if role == "MANAGER":
        scoped_kpis = {
            "scope": "DEPARTMENT",
            "department": dept,
            "pendingApprovals": kpis.get("pendingApprovals", 0),
            "departmentAssignedAssets": kpis.get("departmentAssignedAssets", 0),
            "staffMembers": kpis.get("staffMembers", 0),
            "activeRequests": kpis.get("activeRequests", 0),
            "approvedRequests": kpis.get("approvedRequests", 0)
        }
        res = dashboard_data.copy()
        res["data"] = {
            "scope": "DEPARTMENT",
            "department": dept,
            "kpis": scoped_kpis
        }
        return res

    if role == "STAFF":
        username = user.get("username", "Staff")
        first_name = user.get("firstName") or username
        scoped_kpis = {
            "scope": "PERSONAL",
            "username": username,
            "firstName": first_name,
            "department": dept,
            "myAssignedAssets": kpis.get("myAssignedAssets", 0),
            "myPurchaseRequests": kpis.get("myPurchaseRequests", 0),
            "myApprovedPRs": kpis.get("myApprovedPRs", 0),
            "myPendingRequests": kpis.get("myPendingRequests", 0)
        }
        res = dashboard_data.copy()
        res["data"] = {
            "scope": "PERSONAL",
            "username": username,
            "department": dept,
            "kpis": scoped_kpis
        }
        return res

    return dashboard_data


def filter_employee_assets(user: dict, asset_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Access: All department staff, Managers, CEO, and Admin can access employee assets.
    Returns all employee assets without filtering/scoping.
    """
    return asset_data

def filter_invoices(user: dict, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Filters Invoices dynamically in-memory based on user scope.
    """
    if not invoice_data or not invoice_data.get("success"):
        return invoice_data
        
    invoices = invoice_data.get("data", {}).get("invoices", [])
    if not invoices:
        return invoice_data
        
    role = str(user.get("role", "")).upper().strip()
    dept = str(user.get("department", "")).upper().strip()
    
    is_accounts_manager = (role == "MANAGER" and dept == "ACCOUNTS")
    if role in ["CEO", "ADMIN"] or is_accounts_manager:
        return invoice_data
        
    filtered = []
    for inv in invoices:
        # Match by department
        inv_dept = str(inv.get("department", "")).upper().strip()
        if not inv_dept or inv_dept == dept:
            filtered.append(inv)
            
    res = invoice_data.copy()
    res["data"] = invoice_data.get("data", {}).copy()
    res["data"]["invoices"] = filtered
    return res

def filter_purchase_orders(user: dict, po_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Filters Purchase Orders dynamically in-memory based on user scope.
    """
    if not po_data or not po_data.get("success"):
        return po_data
        
    pos = po_data.get("data", {}).get("purchaseOrders", [])
    if not pos:
        return po_data
        
    role = str(user.get("role", "")).upper().strip()
    dept = str(user.get("department", "")).upper().strip()
    user_id = user.get("user_id")
    
    is_accounts_manager = (role == "MANAGER" and dept == "ACCOUNTS")
    if role in ["CEO", "ADMIN"] or is_accounts_manager:
        return po_data
        
    filtered = []
    if role == "MANAGER":
        for po in pos:
            po_dept = str(po.get("department", "")).upper().strip()
            if not po_dept or po_dept == dept:
                filtered.append(po)
    elif role == "STAFF":
        for po in pos:
            requester = po.get("requester", {})
            requester_id = po.get("requestedBy") or po.get("userId") or (requester.get("id") if isinstance(requester, dict) else None)
            if requester_id == user_id:
                filtered.append(po)
            elif not requester_id:
                po_dept = str(po.get("department", "")).upper().strip()
                if po_dept == dept:
                    filtered.append(po)
            
    res = po_data.copy()
    res["data"] = po_data.get("data", {}).copy()
    res["data"]["purchaseOrders"] = filtered
    return res

def filter_users(user: dict, users_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Filters users to only show the manager's reporting team members.
    """
    if not users_data or not users_data.get("success"):
        return users_data
        
    users_list = users_data.get("data", {}).get("users", [])
    if not users_list:
        return users_data
        
    role = str(user.get("role", "")).upper().strip()
    if role in ["CEO", "ADMIN"]:
        return users_data
        
    if role == "MANAGER":
        mgr_id = user.get("user_id")
        filtered = []
        for u in users_list:
            u_manager_id = u.get("managerId") or u.get("manager_id") or (u.get("manager", {}).get("id") if isinstance(u.get("manager"), dict) else None)
            if u_manager_id is not None and mgr_id is not None and str(u_manager_id).strip() == str(mgr_id).strip():
                filtered.append(u)
        res = users_data.copy()
        res["data"] = users_data.get("data", {}).copy()
        res["data"]["users"] = filtered
        return res
        
    res = users_data.copy()
    res["data"] = users_data.get("data", {}).copy()
    res["data"]["users"] = []
    return res

def filter_suppliers(user: dict, supplier_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Filters suppliers dynamically in-memory based on user scope.
    Rules:
    - CEO/Admin/Manager: Allowed to view suppliers.
    - Staff: Denied access.
    """
    if not supplier_data or not supplier_data.get("success"):
        return supplier_data
        
    role = str(user.get("role", "")).upper().strip()
    if role in ["CEO", "ADMIN", "MANAGER"]:
        return supplier_data
        
    # Return empty list and unauthorized error message
    res = supplier_data.copy()
    res["data"] = supplier_data.get("data", {}).copy()
    res["data"]["suppliers"] = []
    res["success"] = False
    res["error"] = "🔒 You don't have permission to access this information."
    return res


def filter_expenses(user: dict, expense_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Filters expenses based on role scope:
    - CEO / Admin: Access to all organization expenses.
    - Manager: Access to department expenses.
    - Staff: Access to own submitted expenses only.
    """
    if not expense_data or not expense_data.get("success"):
        return expense_data

    expenses = expense_data.get("data", {}).get("expenses", []) or expense_data.get("data", {}).get("items", [])
    if not expenses:
        return expense_data

    role = str(user.get("role", "")).upper().strip()
    dept = str(user.get("department", "")).upper().strip()
    user_id = user.get("user_id")

    if role in ["CEO", "ADMIN"]:
        return expense_data

    filtered = []
    if role == "MANAGER":
        for exp in expenses:
            exp_dept = str(exp.get("department", "")).upper().strip()
            if not exp_dept or exp_dept == dept:
                filtered.append(exp)
    elif role == "STAFF":
        for exp in expenses:
            exp_user_id = exp.get("userId") or exp.get("requestedBy") or (exp.get("user", {}).get("id") if isinstance(exp.get("user"), dict) else None)
            if exp_user_id == user_id:
                filtered.append(exp)
            elif not exp_user_id:
                exp_dept = str(exp.get("department", "")).upper().strip()
                if exp_dept == dept:
                    filtered.append(exp)

    res = expense_data.copy()
    res["data"] = expense_data.get("data", {}).copy()
    res["data"]["expenses"] = filtered
    return res


def filter_supplier_categories(user: dict, cat_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dynamically passes through live Supplier Categories from the backend API/database.
    Any category added, edited, or deleted in the backend database will be
    immediately and automatically reflected in the chatbot in real-time.
    """
    if not cat_data or not cat_data.get("success"):
        return cat_data
        
    categories = cat_data.get("data", [])
    if isinstance(categories, dict):
        categories = categories.get("categories", []) or categories.get("items", [])
    if not isinstance(categories, list):
        return cat_data
        
    filtered = []
    seen = set()
    for c in categories:
        name = str(c.get("name") or c.get("categoryName") or "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            c_copy = c.copy()
            c_copy["name"] = name
            filtered.append(c_copy)
            
    res = cat_data.copy()
    res["data"] = filtered
    return res


def settings_allow_debug() -> bool:
    try:
        from config import settings
        return settings.ALLOW_DEBUG_LOGGING
    except ImportError:
        return False
