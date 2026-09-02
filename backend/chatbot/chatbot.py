import json
import logging
import re
import asyncio
from typing import Dict, Any, List, Optional, Tuple

from google import genai
from google.genai import types

from config import settings
from auth.authentication import verify_and_get_user
from auth.authorization import check_permission
from auth.scoping import filter_purchase_requests, filter_dashboard_data, filter_employee_assets, filter_invoices, filter_purchase_orders
from chatbot.tool_registry import execute_tool
from chatbot.formatters import (
    format_locations_text,
    format_assets_text,
    format_procurement_text,
    format_dashboard_text,
    format_alerts_text
)

logger = logging.getLogger(__name__)

# Initialize the Gemini client
try:
    if settings.GEMINI_API_KEY:
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        model_name = settings.GEMINI_MODEL
    else:
        client = None
        model_name = ""
        logger.warning("GEMINI_API_KEY is not set. Chatbot will not function correctly.")
except Exception as e:
    logger.error(f"Error initializing Gemini client: {e}")
    client = None

# In-memory session chat histories
CHAT_HISTORIES: Dict[str, List[Dict[str, str]]] = {}

# Map tool names to Resource + Action for the permission engine
TOOL_RESOURCES: Dict[str, Tuple[str, str]] = {
    "get_dashboard_overview": ("dashboard", "VIEW"),
    "get_quick_stats": ("dashboard", "VIEW"),
    "get_inventory_summary": ("dashboard", "VIEW"),
    "get_alerts": ("dashboard", "VIEW"),
    "get_recent_assets": ("station_assets", "VIEW"),
    "get_locations": ("locations", "VIEW"),
    "get_asset_types": ("asset_types", "VIEW"),
    "get_assets": ("station_assets", "VIEW"), 
    "get_ho_assets": ("employee_assets", "VIEW"),
    "get_purchase_requests": ("purchase_requests", "VIEW"),
    "get_workflow_status": ("purchase_requests", "VIEW"),
    "get_purchase_orders": ("purchase_orders", "VIEW"),
    "get_suppliers": ("suppliers", "VIEW"),
    "get_supplier_categories": ("supplier_categories", "VIEW"),
    "get_supplier_kart": ("supplier_kart", "VIEW"),
    "get_supplier_cart": ("supplier_kart", "VIEW"),
    "get_my_cart": ("my_cart", "VIEW"),
    "get_procurement_cart": ("my_cart", "VIEW"),
    "get_departments": ("departments", "VIEW"),
    "get_invoices": ("invoices", "VIEW"),
    "get_payments": ("payments", "VIEW"),
    "get_users": ("users", "VIEW"),
    "get_expenses": ("expenses", "VIEW"),
    "get_petty_cash": ("expenses", "VIEW"),
    "get_supplier_performance": ("suppliers", "VIEW"),
    "get_procurement_summary": ("purchase_orders", "VIEW"),
    "get_department_spending": ("expenses", "VIEW"),
    "get_monthly_approved_cost": ("expenses", "VIEW"),
    "get_products": ("products", "VIEW")
}

def log_chatbot_request(question: str, intent: str, endpoint: str, permission: str, num_records: int, gemini_calls: int, status: str, user: dict = None, resource: str = None, action: str = None, scope: str = None):
    """
    Standard developer log output formatted exactly as requested.
    """
    user_id = user.get("user_id") if user else "None"
    username = user.get("username") if user else "None"
    role = user.get("role") if user else "None"
    dept = user.get("department") if user else "None"
    
    logger.info(
        f"\n--- Chatbot Request Log ---\n"
        f"User ID: {user_id}\n"
        f"Username: {username}\n"
        f"Role: {role}\n"
        f"Department: {dept}\n"
        f"Requested Resource: {resource or 'None'}\n"
        f"Requested Action: {action or 'None'}\n"
        f"Permission Result: {permission}\n"
        f"Applied Scope: {scope or 'None'}\n"
        f"Question: {question}\n"
        f"Intent: {intent}\n"
        f"Inventory API: {endpoint}\n"
        f"Authorized Records: {num_records}\n"
        f"Gemini calls: {gemini_calls}\n"
        f"Response status: {status}\n"
        f"---------------------------"
    )

def is_state_changing_request(message: str) -> bool:
    """
    Analyzes user message to detect state-changing intent (CREATE, UPDATE, DELETE, APPROVE).
    Uses contextual regex to prevent blocking read-only questions like 'why was X deleted?'.
    """
    msg = message.lower().strip()
    
    write_verbs = r"\b(delete|remove|create|add|update|change|approve|upload|reject)\b"
    resources = r"\b(location|asset|pr|po|purchase|quote|user|item|product|category)\b"
    
    # Match direct action queries: "delete location Chennai Central", "create PR"
    if re.search(r"^" + write_verbs + r"\s+" + resources, msg):
        return True
        
    # Match polite request actions: "please delete...", "can you approve..."
    if re.search(r"\b(please|can you|should we|go ahead and)\s+" + write_verbs + r"\s+" + resources, msg):
        return True
        
    return False

def match_deterministic_route(message: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Deterministic intent router mapping user queries to registered Inventory APIs.
    Bypasses Gemini intent detection entirely (0 calls).
    """
    msg = message.lower().strip()
    
    # 0. Entity prefix tagging detection (highly specific routing)
    if "pr@" in msg or "pnr@" in msg:
        return "get_purchase_requests", {}
    if "po@" in msg:
        return "get_purchase_orders", {}
    if "inv@" in msg:
        return "get_invoices", {}
    if "ast@" in msg:
        if "emp" in msg or "nmc_ast_emp" in msg:
            return "get_ho_assets", {}
        return "get_assets", {}

    # 2. Assets (Station Assets vs Employee / HO Assets)
    if any(k in msg for k in ["asset", "nmc_ast", "signal lamp", "lamp", "station asset", "station_asset", "employee asset", "ho asset"]):
        if any(k in msg for k in ["station asset", "station_asset", "station assets", "station"]):
            return "get_assets", {}
        if any(k in msg for k in ["employee asset", "employee assets", "staff asset", "head office", "ho asset"]) or re.search(r'\b(ho|emp|employee|staff)\b', msg):
            return "get_ho_assets", {}
        return "get_assets", {}

    # 3. Products / Delivered Inventory / Arrivals
    if any(k in msg for k in ["product", "item", "delivered", "arrival", "stock", "quantity"]):
        return "get_products", {}

    # 4. Workflow Status & Purchase Request Approvals Flow
    if any(k in msg for k in ["workflow", "approval status", "approval flow", "approvals flow", "prs i approved", "staff workflow", "department workflow"]):
        return "get_workflow_status", {}

    # 4.5 Purchase Requests (PR)
    if "purchase request" in msg or re.search(r'\bprs?\b', msg):
        return "get_purchase_requests", {}

    # 5. Purchase Orders (PO)
    if "purchase order" in msg or re.search(r'\bpos?\b', msg):
        return "get_purchase_orders", {}

    # 6. Supplier Kart (Vendor product catalog)
    if any(k in msg for k in ["supplier kart", "supplier cart", "supplier's kart", "supplier's cart", "vendor kart", "vendor cart", "kart"]):
        return "get_supplier_kart", {}

    # 7. My Cart / Procurement Cart (User's personal selected items)
    if any(k in msg for k in ["my cart", "my kart", "own cart", "own kart", "user cart", "user kart", "personal cart", "cart", "procurement cart", "procurement kart"]):
        return "get_my_cart", {}

    # 7.5 Supplier Categories & Classifications (Restricted to CEO/Admin/Manager)
    if any(k in msg for k in ["supplier category", "supplier categories", "supplier classification", "category list", "supplier cat", "categories", "category"]):
        return "get_supplier_categories", {}

    # 8. Suppliers Directory & Details (Restricted to CEO/Admin/Manager)
    if any(k in msg for k in ["supplier", "vendor", "abc company", "amazon supplier", "dell india"]):
        return "get_suppliers", {}

    # 6. Expenses / Cost / Department Spending
    if any(k in msg for k in ["expense", "spending", "cost", "monthly approved cost", "approved cost"]):
        if "approved cost" in msg or "monthly approved" in msg:
            year_match = re.search(r'\b(20\d{2})\b', msg)
            year = int(year_match.group(1)) if year_match else 2026
            return "get_monthly_approved_cost", {"year": year}
        return "get_expenses", {}

    # 7. Dashboard / Stats
    if any(k in msg for k in ["dashboard", "overview", "quick stats", "stats"]):
        return "get_dashboard_overview", {}

    # 8. Alerts
    if "alert" in msg:
        return "get_alerts", {}

    # 9. Departments
    if "department" in msg:
        return "get_departments", {}

    # 10. Invoices
    if "invoice" in msg:
        return "get_invoices", {}

    # 11. Payments
    if "payment" in msg:
        return "get_payments", {}

    # 12. Users & Roles Directory
    if any(k in msg for k in ["user", "users", "user list", "all users", "team members", "user and role", "users and roles", "staff list", "system users", "roles"]):
        return "get_users", {}

    # 13. Petty Cash
    if "petty cash" in msg:
        return "get_petty_cash", {}
        
    # 1. Locations / Station Code (Moved down to avoid masking other core resource queries)
    if any(k in msg for k in ["location", "station", "station code", "stationcode", "where is the code"]):
        return "get_locations", {}
    states = ["tamil nadu", "kerala", "karnataka", "andhra pradesh", "maharashtra", "delhi"]
    if any(state in msg for state in states):
        return "get_locations", {}
        
    return None

def get_number_of_records(func_name: str, api_data: Dict[str, Any]) -> int:
    """
    Extracts the number of records returned in the API data payload for logging.
    """
    if not api_data or not api_data.get("success"):
        return 0
    data = api_data.get("data", {})
    if not data:
        return 0
    if isinstance(data, list):
        return len(data)
        
    # Look for lists inside typical keys
    for k in ["purchaseRequests", "purchaseOrders", "locations", "assets", "suppliers", "categories", "expenses", "users", "departments", "invoices", "payments", "alerts"]:
        if isinstance(data, dict) and k in data and isinstance(data[k], list):
            return len(data[k])
            
    # Try generic dictionary counting
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, list):
                return len(v)
            
    return 1

def apply_backend_scoping(user: dict, resource: str, api_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Applies data filtering in-memory based on the user's specific access scope.
    Ensures unauthorized data never reaches Gemini.
    """
    if "error" in api_data:
        return api_data
        
    if resource == "purchase_requests":
        return filter_purchase_requests(user, api_data)
    elif resource == "dashboard":
        return filter_dashboard_data(user, api_data)
    elif resource == "employee_assets":
        return filter_employee_assets(user, api_data)
    elif resource == "suppliers":
        from auth.scoping import filter_suppliers
        return filter_suppliers(user, api_data)
    elif resource in ["supplier_categories", "supplier_category", "category"]:
        from auth.scoping import filter_supplier_categories
        return filter_supplier_categories(user, api_data)
    elif resource == "invoices":
        from auth.scoping import filter_invoices
        return filter_invoices(user, api_data)
    elif resource == "purchase_orders":
        from auth.scoping import filter_purchase_orders
        return filter_purchase_orders(user, api_data)
    elif resource == "users":
        from auth.scoping import filter_users
        return filter_users(user, api_data)
    elif resource == "expenses":
        from auth.scoping import filter_expenses
        return filter_expenses(user, api_data)
        
    return api_data

LLM_STATUS = {"is_offline": False, "last_error": None}

def get_llm_offline_status() -> bool:
    """
    Returns True if the LLM/Gemini service is offline or has exceeded its quota limit.
    """
    return LLM_STATUS.get("is_offline", False)

async def generate_chat_response(user_question: str, api_data: Dict[str, Any], user_info: dict) -> str:
    """
    Converts the authorized API response JSON into a natural conversational
    answer using exactly ONE Gemini API call.
    Does not send tokens, keys, secrets, passwords, or personal details to Gemini.
    """
    if not client:
        LLM_STATUS["is_offline"] = True
        return "The AI assistant is not properly configured. Please check the Gemini API key."
        
    role = user_info.get("role", "Unknown")
    dept = user_info.get("department", "Unknown")
    
    # Minimize user info passed to Gemini - send only role and department (no IDs, emails, or credentials)
    gemini_user_context = f"Role: {role}, Department: {dept}"
    
    system_instruction = """You are the Inventory AI Chatbot.
Convert the provided authorized Inventory API data into a warm, natural, and conversational chatbot answer (avoid using database key-value bullet lists; instead, structure the answer in friendly, human-like sentences and paragraphs).

Rules:
1. Answer the user's question using ONLY the provided Inventory data. Write in conversational sentence formations to make the information easy to understand.
2. Do not invent or hallucinate information.
3. Do not expose raw JSON or present raw key-value listings (like "Status: SUBMITTED", "Priority: MEDIUM"). Instead, write: "The request has been submitted with a medium priority level."
4. Do not mention internal API implementation details unless useful.
5. Always keep responses polite, concise, professional, and directly relevant to what was asked.
6. When displaying costs, prepend the Indian Rupee symbol (₹).
7. Format department names and locations cleanly.
8. If no records match, give a helpful, courteous response.
9. **Role Scoping Adherence:** All data provided in AUTHORIZED INVENTORY DATA has already been strictly scoped and pre-filtered to the user's authorized role and department. Treat all records in the data as the complete and authoritative truth for this user.
10. Do not provide or mention information outside the user's authorized scope.
11. **Approval Chain Rule:** For purchase requests awaiting multi-level approvals: if a lower level (e.g. Level 1) is currently PENDING/AWAITING approval, do NOT mention any upcoming levels (e.g. Level 2, Level 3). Stop at the active pending level itself. Do not mention that subsequent approvals are awaited since we stop at the active pending level itself.
12. **Descriptive User Roles Rule:** When listing or describing users and their roles, do not refer to them generically as just "Manager" or "Staff". Always combine their role and department to state precisely what manager or staff they are (for example: "IT Manager", "Finance Manager", "Sales Manager", "IT Staff", "Sales Staff", etc.). If no department name is present, you may state their raw role.
13. **CEO/Admin Full Access Rule:** If the user role is CEO or ADMIN, they have full management access to everything in the company. Therefore, if they ask for "my assets", "my PRs", "my expenses", "my invoices", or "my orders", you must list and summarize ALL records provided in the data rather than filtering for items specifically assigned to their name or user ID, because they own and oversee all company items. Do not say that they have no assets or requests assigned to them if records exist in the data.
14. **Supplier Details Rule:** When formatting authorized supplier details, include their Name, Category, Contact Person, Phone, Email, and Status.
16. **Purchase Requests Link Rule:** When the user asks to view or show purchase requests (e.g., "show my purchase request", "show purchase requests", "my PRs", "purchase request"):
- Give a brief, courteous summary stating the number of purchase requests available in their scope (their personal PRs for Staff; all company PRs for CEO/Admin).
- Provide the direct page link:
  `[🔗 View Purchase Requests](https://inventory.indianrailwayads.com/procurement?tab=requests)`
- Keep the response clean and concise with the link so the user can directly open the web page.
- If the user explicitly asks about a specific PR number (e.g., `PR2026080004`), summarize that specific PR's details along with the link."""

    prompt = f"""USER CONTEXT:
{gemini_user_context}

USER QUESTION:
{user_question}

AUTHORIZED INVENTORY DATA:
{json.dumps(api_data, indent=2)}

Please generate the final conversational chatbot response."""

    models_to_try = [m for m in [model_name, "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-flash-latest", "gemini-flash-lite-latest"] if m]
    # Remove duplicates while preserving order
    models_to_try = list(dict.fromkeys(models_to_try))

    last_exc = None
    for current_model in models_to_try:
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=current_model,
                    contents=[prompt],
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.2,
                    )
                ),
                timeout=30.0
            )
            LLM_STATUS["is_offline"] = False
            LLM_STATUS["last_error"] = None
            return response.text.strip()
        except Exception as e:
            last_exc = e
            logger.warning(f"Gemini model '{current_model}' failed ({e}). Trying next model...")

    logger.error(f"All Gemini models failed. Last error: {last_exc}")
    LLM_STATUS["is_offline"] = True
    LLM_STATUS["last_error"] = str(last_exc)
    raise RuntimeError(f"Gemini failed: {last_exc}")

async def handle_chat(message: str, mentions: Optional[List[dict]] = None, entities: Optional[List[dict]] = None, user_token: Optional[str] = None) -> str:
    # 0. Block Out-of-Scope / AI Queries & Greetings
    msg = message.lower().strip()
    if ("what is ai" in msg or "define ai" in msg or "explain ai" in msg or msg == "ai") or (("ai" in msg or "artificial intelligence" in msg) and not any(k in msg for k in ["asset", "location", "station", "pr", "po", "request", "order", "inventory", "supplier"])):
        # Greetings/Blocked questions bypass Gemini completely (0 calls)
        log_chatbot_request(message, "out_of_scope", "None", "Blocked", 0, 0, "blocked")
        return "I can currently help only with Inventory Management related information."
        
    if msg in ["hello", "hi", "hey", "greetings", "hi there"]:
        log_chatbot_request(message, "greeting", "None", "Allowed", 0, 0, "success")
        return "Hello! I am the Inventory AI Assistant. How can I help you manage your inventory, assets, or procurement today?"

    if msg in ["how to use the assistant", "how to use"]:
        log_chatbot_request(message, "how_to_use", "None", "Allowed", 0, 0, "success")
        return (
            "You can ask me about Inventory assets, locations, purchase requests, invoices, purchase orders, "
            "expenses and dashboard information. Your results are based on your account permissions. "
            "To query specific items, you can tag them in your question: use AST@ for Assets, PR@ for Purchase Requests, "
            "INV@ for Invoices, PO@ for Purchase Orders, or @ to select a User or Manager."
        )

    # 1. Block State-Changing Intents (Read-Only Check)
    if is_state_changing_request(message):
        log_chatbot_request(message, "write_action", "None", "Blocked", 0, 0, "blocked")
        return "I can provide Inventory information, but I cannot perform state-changing actions (such as creation, deletion, or approval) through the chatbot."

    # 2. Authenticate the request using incoming session token (or fallback config)
    active_token = user_token or settings.INVENTORY_ACCESS_TOKEN
    user_info = await verify_and_get_user(active_token)
    if "error" in user_info:
        log_chatbot_request(message, "authenticate", "None", "Denied", 0, 0, "auth_failed")
        return user_info["error"]

    user_role = str(user_info.get("role", "")).upper().strip()
    user_manager_id = user_info.get("managerId")

    # 2.1 Handle User Profile Queries
    if any(k in msg for k in ["profile", "who am i", "my role", "my account", "my info", "my details", "about me", "logged in as", "my user", "who is logged in", "current user"]):
        from auth.authentication import resolve_user_profile
        manager_profile = None
        if user_info.get("managerId"):
            manager_profile = await resolve_user_profile(user_info.get("managerId"), None, None)
        from chatbot.formatters import format_user_profile_text
        profile_text = format_user_profile_text(user_info, manager_profile)
        log_chatbot_request(message, "user_profile", "auth/profile", "Allowed", 1, 0, "success", user=user_info, resource="users", action="VIEW", scope="OWN")
        return profile_text

    # 2.2 Staff Global Organization Scope Check for Workflows, PRs & POs
    if user_role == "STAFF":
        if "workflow" in msg:
            # Check if staff is asking for all/company workflows
            if ("all" in msg or "entire" in msg or "every" in msg or "org" in msg or "company" in msg) and not any(k in msg for k in ["my", "mine", "own"]):
                log_chatbot_request(message, "permission_denied", "procurement/purchase-requests", "Denied (Staff All Workflows)", 0, 0, "permission_denied", user=user_info, resource="purchase_requests", action="VIEW", scope="DENIED")
                return "🔒 You do not have permission to view all workflow statuses across the organization. You can only view workflow status for purchase requests created by you. Please ask: **'Show my workflow status'**."
            
            # Check if staff is asking for another user's workflow (e.g. "Show Dinesh's workflow")
            all_known_users = ["dinesh", "siva", "domic", "asir", "pugal", "srini", "admin", "ceo", "allen123"]
            for target_u in all_known_users:
                if target_u in msg and target_u != str(user_info.get("username", "")).lower():
                    log_chatbot_request(message, "permission_denied", "procurement/purchase-requests", f"Denied (Staff {target_u.title()} Workflow)", 0, 0, "permission_denied", user=user_info, resource="purchase_requests", action="VIEW", scope="DENIED")
                    return f"🔒 You don't have permission to access {target_u.title()}'s workflow status. You can only view workflow status for purchase requests you created."

        if ("all" in msg or "entire" in msg or "every" in msg or "org" in msg or "company" in msg) and not any(k in msg for k in ["my", "mine", "own", "assigned"]):
            if any(k in msg for k in ["purchase request", "purchase requests"]) or re.search(r'\ball\s+(?:the\s+)?prs?\b', msg):
                log_chatbot_request(message, "permission_denied", "procurement/purchase-requests", "Denied (Staff All PRs)", 0, 0, "permission_denied", user=user_info, resource="purchase_requests", action="VIEW", scope="DENIED")
                return "🔒 You do not have permission to view all purchase requests across the organization. You can only view purchase requests created by you. Please ask: **'Show my purchase requests'**."
                
            if any(k in msg for k in ["purchase order", "purchase orders"]) or re.search(r'\ball\s+(?:the\s+)?pos?\b', msg):
                log_chatbot_request(message, "permission_denied", "procurement/purchase-orders", "Denied (Staff All POs)", 0, 0, "permission_denied", user=user_info, resource="purchase_orders", action="VIEW", scope="DENIED")
                return "🔒 You do not have permission to view all purchase orders across the organization. You can only view purchase orders related to your requests. Please ask: **'Show my purchase orders'**."

    # 2.5 Advanced @Mention & Entity Security Validation
    mentioned_ids = []
    if mentions:
        for m in mentions:
            mentioned_ids.append(m.get("user_id"))
            
    text_mentions = re.findall(r'(?<!PR)(?<!PNR)(?<!INV)(?<!PO)(?<!AST)@([a-zA-Z0-9_]+)', message)
    if text_mentions:
        from auth.authentication import resolve_user_profile
        for m_uname in text_mentions:
            profile = await resolve_user_profile(None, m_uname, None)
            if profile:
                mentioned_ids.append(profile.get("id"))
            else:
                mentioned_ids.append(-999)
                
    # Parse manual references from message text
    man_prs = []
    # Match PR@xxxx or PNR@xxxx
    for r in re.findall(r'(?:PR|PNR)@([a-zA-Z0-9_-]+)', message, re.IGNORECASE):
        man_prs.append(r)
        if not r.lower().startswith("pr"):
            man_prs.append(f"pr{r}")
    # Match PRxxxx or PNRxxxx (e.g. PR2026080003)
    for r in re.findall(r'\b(?:PR|PNR)(\d+[a-zA-Z0-9_-]*)\b', message, re.IGNORECASE):
        man_prs.append(f"pr{r}")
        man_prs.append(r)

    man_invs = re.findall(r'INV@([a-zA-Z0-9_-]+)', message, re.IGNORECASE)
    man_pos = re.findall(r'PO@([a-zA-Z0-9_-]+)', message, re.IGNORECASE)
    man_assets = re.findall(r'AST@([a-zA-Z0-9_-]+)', message, re.IGNORECASE)
    
    # Collect all reference checks (lowercased)
    all_pr_refs = [str(e.get("reference")).lower() for e in entities if e.get("type") == "purchase_request"] if entities else []
    all_pr_refs.extend([r.lower() for r in man_prs])

    # Staff user tagging check: only tag approvers of tagged PR, fallback to manager if no PR tagged
    if user_role == "STAFF" and mentioned_ids:
        if all_pr_refs:
            from services.inventory_api import get_purchase_requests
            data = await get_purchase_requests()
            data = filter_purchase_requests(user_info, data)
            prs = data.get("data", {}).get("purchaseRequests", []) if data.get("success") else []
            
            tagged_prs = []
            for ref in all_pr_refs:
                for pr in prs:
                    if str(pr.get("prNumber")).lower() == ref or str(pr.get("id")) == ref:
                        tagged_prs.append(pr)
                        
            allowed_approver_ids = set()
            for pr in tagged_prs:
                approvals = pr.get("approvals", []) or []
                for app in approvals:
                    if isinstance(app, dict):
                        approver_id = app.get("approverId") or (app.get("approver", {}).get("id") if isinstance(app.get("approver"), dict) else None)
                        if approver_id:
                            allowed_approver_ids.add(approver_id)
                            
            for m_id in mentioned_ids:
                if m_id not in allowed_approver_ids:
                    log_chatbot_request(message, "mention_validation", f"PR-approver-check: {m_id}", "Denied", 0, 0, "unauthorized_pr_mention")
                    return "🔒 You can only tag users who are selected as approvers for this purchase request."
        else:
            for m_id in mentioned_ids:
                if m_id != user_manager_id:
                    log_chatbot_request(message, "mention_validation", "None", "Denied", 0, 0, "unauthorized_mention")
                    return "🔒 You don't have permission to tag this item or user."
    
    all_inv_refs = [str(e.get("reference")).lower() for e in entities if e.get("type") == "invoice"] if entities else []
    all_inv_refs.extend([r.lower() for r in man_invs])
    
    all_po_refs = [str(e.get("reference")).lower() for e in entities if e.get("type") == "purchase_order"] if entities else []
    all_po_refs.extend([r.lower() for r in man_pos])
    
    all_asset_refs = [str(e.get("reference")).lower() for e in entities if e.get("type") == "asset"] if entities else []
    all_asset_refs.extend([r.lower() for r in man_assets])

    # A. Validate Purchase Requests
    if all_pr_refs:
        from services.inventory_api import get_purchase_requests
        data = await get_purchase_requests()
        data = filter_purchase_requests(user_info, data)
        prs = data.get("data", {}).get("purchaseRequests", []) if data.get("success") else []
        logger.info(f"DEBUG VALIDATION: user_id={user_info.get('user_id')} username={user_info.get('username')} role={user_info.get('role')}")
        logger.info(f"DEBUG VALIDATION: pr_refs={all_pr_refs}")
        logger.info(f"DEBUG VALIDATION: allowed_pr_numbers={[pr.get('prNumber') for pr in prs]} allowed_ids={[pr.get('id') for pr in prs]}")
        for ref in all_pr_refs:
            ref_clean = ref.lower().replace("pnr", "pr")
            if not ref_clean.startswith("pr") and ref_clean.isdigit():
                ref_clean = f"pr{ref_clean}"
            match = any(
                str(pr.get("prNumber", "")).lower() in [ref.lower(), ref_clean.lower(), f"pr{ref.lower()}"]
                or str(pr.get("id")) == ref
                for pr in prs
            )
            logger.info(f"DEBUG VALIDATION: ref={ref} match_found={match}")
            if not match:
                log_chatbot_request(message, "entity_validation", f"PR: {ref}", "Denied", 0, 0, "unauthorized_entity")
                return "🔒 You don't have permission to tag this item or user."

    # B. Validate Invoices
    if all_inv_refs:
        from services.inventory_api import get_invoices
        data = await get_invoices()
        data = filter_invoices(user_info, data)
        invs = data.get("data", {}).get("invoices", []) if data.get("success") else []
        for ref in all_inv_refs:
            if not any(str(inv.get("invoiceNumber")).lower() == ref or str(inv.get("id")) == ref for inv in invs):
                log_chatbot_request(message, "entity_validation", f"Invoice: {ref}", "Denied", 0, 0, "unauthorized_entity")
                return "🔒 You don't have permission to tag this item or user."

    # C. Validate Purchase Orders
    if all_po_refs:
        from services.inventory_api import get_purchase_orders
        data = await get_purchase_orders()
        data = filter_purchase_orders(user_info, data)
        pos = data.get("data", {}).get("purchaseOrders", []) if data.get("success") else []
        for ref in all_po_refs:
            if not any(str(po.get("poNumber")).lower() == ref or str(po.get("id")) == ref for po in pos):
                log_chatbot_request(message, "entity_validation", f"PO: {ref}", "Denied", 0, 0, "unauthorized_entity")
                return "🔒 You don't have permission to tag this item or user."

    # D. Validate Assets
    if all_asset_refs:
        from services.inventory_api import get_assets
        from auth.scoping import filter_employee_assets
        data = await get_assets()
        data = filter_employee_assets(user_info, data)
        assets = data.get("data", {}).get("assets", []) if data.get("success") else []
        for ref in all_asset_refs:
            if not any(str(asset.get("assets_code")).lower() == ref or str(asset.get("id")) == ref for asset in assets):
                log_chatbot_request(message, "entity_validation", f"Asset: {ref}", "Denied", 0, 0, "unauthorized_entity")
                return "🔒 You don't have permission to tag this asset."

    # 3. Match Deterministic Route
    route = match_deterministic_route(message)
    if route:
        func_name, args = route
        resource, action = TOOL_RESOURCES.get(func_name, ("general", "VIEW"))
        
        # Permission check
        if not check_permission(user_info, resource, action):
            log_chatbot_request(message, func_name, f"GET /{resource}", "Denied", 0, 0, "unauthorized", user=user_info, resource=resource, action=action, scope="DENIED")
            if resource in ["suppliers", "supplier"]:
                return "🔒 You don't have permission to access supplier information."
            return "🔒 You don't have permission to access this information."
            
        # Execute the database API tool
        api_data = await execute_tool(func_name, args)
        
        # Apply strict scoping checks in-memory before Gemini receives it
        api_data = apply_backend_scoping(user_info, resource, api_data)
        
        # Check if scoping returned an error
        if isinstance(api_data, dict) and "error" in api_data:
            log_chatbot_request(message, func_name, f"GET /{resource}", "Allowed (Scoped Error)", 0, 0, "scoped_error", user=user_info, resource=resource, action=action, scope="DENIED")
            return api_data["error"]
            
        num_records = get_number_of_records(func_name, api_data)
        
        # Determine applied scope
        applied_scope = "ALL"
        u_role = str(user_info.get("role", "")).upper().strip()
        u_dept = str(user_info.get("department", "")).upper().strip()
        if u_role == "MANAGER":
            if resource == "purchase_requests":
                applied_scope = "OWN_DEPARTMENT + OWN_DATA + APPROVED_BY_ME"
            else:
                applied_scope = "OWN_DEPARTMENT"
        elif u_role == "STAFF":
            applied_scope = "OWN_DATA"
        
        # Use exactly ONE Gemini call to convert JSON into conversational text
        try:
            response_out = await generate_chat_response(message, api_data, user_info)
            log_chatbot_request(message, func_name, f"GET /{resource}", "Allowed", num_records, 1, "success", user=user_info, resource=resource, action=action, scope=applied_scope)
            return response_out
        except Exception as e:
            import traceback
            logger.error(f"Gemini formatting failed:\n{traceback.format_exc()}")
            LLM_STATUS["is_offline"] = True
            LLM_STATUS["last_error"] = str(e)
            log_chatbot_request(message, func_name, f"GET /{resource} (Offline)", "Allowed", num_records, 1, "llm_offline", user=user_info, resource=resource, action=action, scope=applied_scope)
            err_str = str(e)
            if "429" in err_str or "quota" in err_str.lower() or "resource_exhausted" in err_str.lower():
                return "⚠️ The AI Assistant is temporarily unavailable because the AI service quota limit has been reached. Please try again shortly."
            return "⚠️ The AI Assistant is temporarily unable to process this response. Please try again shortly."

    # 4. Fallback to general conversational chat (when no API match is found)
    # This covers general chats/greetings that don't query a database API.
    # Uses exactly ONE Gemini call.
    try:
        system_instruction = "You are the Inventory AI Chatbot. Answer the user's question politely and concisely. If they ask about inventory tasks, guide them to ask specific questions about locations, assets, suppliers, expenses, or procurement."
        
        models_to_try = [m for m in [model_name, "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-flash-latest", "gemini-flash-lite-latest"] if m]
        models_to_try = list(dict.fromkeys(models_to_try))

        last_fallback_err = None
        for current_model in models_to_try:
            try:
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=current_model,
                        contents=[message],
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            temperature=0.4,
                        )
                    ),
                    timeout=30.0
                )
                response_out = response.text.strip()
                LLM_STATUS["is_offline"] = False
                LLM_STATUS["last_error"] = None
                log_chatbot_request(message, "general_fallback", "None", "Allowed", 0, 1, "success")
                return response_out
            except Exception as fe:
                last_fallback_err = fe
                logger.warning(f"General fallback Gemini model '{current_model}' failed ({fe}). Trying next...")

        raise last_fallback_err or RuntimeError("All models failed")
    except Exception as e:
        import traceback
        logger.error(f"General fallback error:\n{traceback.format_exc()}")
        LLM_STATUS["is_offline"] = True
        LLM_STATUS["last_error"] = str(e)
        log_chatbot_request(message, "general_fallback_error", "None", "Allowed", 0, 1, "failed")
        err_str = str(e)
        if "429" in err_str or "quota" in err_str.lower() or "resource_exhausted" in err_str.lower():
            return "⚠️ The AI Assistant is temporarily unavailable because the AI service quota limit has been reached. Please try again shortly."
        return "⚠️ The AI Assistant is temporarily unavailable. Please try again shortly."
