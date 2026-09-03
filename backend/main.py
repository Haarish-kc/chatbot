from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import logging

from chatbot.chatbot import handle_chat
from auth.authentication import verify_and_get_user, resolve_user_profile
from auth.scoping import filter_purchase_requests, filter_invoices, filter_purchase_orders, filter_employee_assets
from services.inventory_api import get_purchase_requests, get_invoices, get_purchase_orders, get_assets
from config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Inventory AI Assistant API")

# Setup CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class EntityTag(BaseModel):
    type: str
    id: Optional[int] = None
    reference: str

class MentionTag(BaseModel):
    user_id: int
    username: str

class ChatRequest(BaseModel):
    message: str
    mentions: Optional[List[MentionTag]] = None
    entities: Optional[List[EntityTag]] = None

class ChatResponse(BaseModel):
    response: str
    is_offline: bool = False

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, authorization: Optional[str] = Header(None)):
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
        
    try:
        from auth.authentication import sanitize_bearer_token
        user_token = sanitize_bearer_token(authorization)

        # Convert Pydantic schemas to standard dictionaries for chatbot processing
        mentions_list = [m.model_dump() for m in request.mentions] if request.mentions else None
        entities_list = [e.model_dump() for e in request.entities] if request.entities else None
        
        # Pass payload down to the chatbot brain
        response_text = await handle_chat(
            message=request.message,
            mentions=mentions_list,
            entities=entities_list,
            user_token=user_token
        )
        from chatbot.chatbot import get_llm_offline_status
        return ChatResponse(response=response_text, is_offline=get_llm_offline_status())
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error processing chat: {error_msg}")
        
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            raise HTTPException(status_code=429, detail="The AI Assistant is currently receiving too many requests. Please wait a few seconds and try again.")
            
        raise HTTPException(status_code=500, detail="I'm unable to retrieve the inventory information right now. Please try again later.")

@app.get("/api/status")
@app.get("/api/health")
async def get_system_status():
    """
    Returns the real-time AI and microservice connectivity status.
    """
    from chatbot.chatbot import get_llm_offline_status
    is_offline = get_llm_offline_status()
    return {
        "status": "ok",
        "is_offline": is_offline,
        "mode": "FALLBACK_OFFLINE" if is_offline else "ONLINE_AI"
    }

@app.get("/api/me")
async def get_current_user_profile(authorization: str = Header(None)):
    """
    Returns the authenticated user's basic profile (name, role, department)
    for display in the frontend UI. Uses the same JWT verification flow.
    """
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1].strip('"\'')
    else:
        token = settings.INVENTORY_ACCESS_TOKEN

    print(f"[DEBUG ME] Requested profile. Token length={len(token) if token else 0}")
    if not token:
        print("[DEBUG ME] No token provided or resolved")
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")

    user_info = await verify_and_get_user(token)
    if "error" in user_info:
        print(f"[DEBUG ME] verify_and_get_user returned error: {user_info['error']}")
        raise HTTPException(status_code=401, detail=user_info["error"])

    print(f"[DEBUG ME] Matched user ID: {user_info.get('user_id')}, username: {user_info.get('username')}")

    first_name = user_info.get("firstName") or str(user_info.get("username", "")).capitalize()
    last_name = user_info.get("lastName", "")
    
    # Try enriching with full profile from Users API if available
    try:
        from services.inventory_api import get_users
        users_data = await get_users()
        if users_data and users_data.get("success"):
            users_list = users_data.get("data", {}).get("users", [])
            target_user_id_str = str(user_info.get("user_id")) if user_info.get("user_id") is not None else None
            target_email = str(user_info.get("email", "")).lower().strip()
            
            for u in users_list:
                u_id_str = str(u.get("id")) if u.get("id") is not None else None
                u_email = str(u.get("email", "")).lower().strip()
                if (target_user_id_str and u_id_str == target_user_id_str) or (target_email and u_email == target_email):
                    if u.get("firstName"): first_name = u.get("firstName")
                    if u.get("lastName"): last_name = u.get("lastName")
                    break
    except Exception as e:
        print(f"[DEBUG ME] Non-critical user enrich failed: {e}")

    full_name = f"{first_name} {last_name}".strip() or user_info.get("username", "")

    result = {
        "name": full_name,
        "firstName": first_name,
        "role": str(user_info.get("role", "")).upper(),
        "department": user_info.get("department", ""),
        "username": user_info.get("username", "")
    }
    print(f"[DEBUG ME] Final returning payload: {result}")
    return result

class AttachmentModel(BaseModel):
    filename: str
    content: str  # Base64 encoded file content
    
class SupportRequest(BaseModel):
    description: str
    issue_type: str
    attachment: Optional[AttachmentModel] = None

@app.post("/api/support")
async def support_endpoint(request: SupportRequest, authorization: str = Header(None)):
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1].strip('"\'')
    else:
        token = settings.INVENTORY_ACCESS_TOKEN
        
    if not token:
        raise HTTPException(status_code=401, detail="🔐 Session expired. Please sign in again.")
        
    user_info = await verify_and_get_user(token)
    if "error" in user_info:
        raise HTTPException(status_code=401, detail=user_info["error"])
        
    from services.email_service import send_support_email
    
    try:
        attachment_dict = request.attachment.model_dump() if request.attachment else None
        success = await send_support_email(
            user_info=user_info,
            description=request.description,
            issue_type=request.issue_type,
            attachment=attachment_dict
        )
        if not success:
            raise HTTPException(
                status_code=500, 
                detail="⚠️ We couldn't send your issue right now. Please try again later."
            )
        return {"success": True, "message": "Your issue has been sent successfully via mail."}
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as e:
        logger.error(f"Support endpoint failed to send email: {e}")
        raise HTTPException(
            status_code=500, 
            detail="⚠️ We couldn't send your issue right now. Please try again later."
        )

class FeedbackRequest(BaseModel):
    rating: Optional[int] = 0
    feedback_text: Optional[str] = ""

@app.post("/api/feedback")
async def feedback_endpoint(request: FeedbackRequest, authorization: str = Header(None)):
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1].strip('"\'')
    else:
        token = settings.INVENTORY_ACCESS_TOKEN
        
    user_info = {}
    if token:
        resolved = await verify_and_get_user(token)
        if "error" not in resolved:
            user_info = resolved
            
    from services.email_service import send_feedback_email
    
    try:
        success = await send_feedback_email(
            user_info=user_info,
            rating=request.rating or 0,
            feedback_text=request.feedback_text or ""
        )
        if not success:
            raise HTTPException(
                status_code=500,
                detail="⚠️ We couldn't send your feedback right now. Please try again later."
            )
        return {"success": True, "message": "Your feedback has been submitted successfully."}
    except Exception as e:
        logger.error(f"Feedback endpoint failed to send email: {e}")
        raise HTTPException(
            status_code=500,
            detail="⚠️ We couldn't send your feedback right now. Please try again later."
        )

@app.get("/api/mentions/allowed")
async def allowed_mentions(pr_number: Optional[str] = None, authorization: str = Header(None)):
    """
    Dynamically resolves the currently authenticated user and returns allowed users.
    If pr_number is provided, returns ONLY the selected approvers for that PR.
    For Staff users with no PR context, returns ONLY their assigned Manager.
    """
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1].strip('"\'')
    else:
        token = settings.INVENTORY_ACCESS_TOKEN
        
    if not token:
        raise HTTPException(status_code=401, detail="🔐 Session expired. Please sign in again.")
        
    user_info = await verify_and_get_user(token)
    if "error" in user_info:
        raise HTTPException(status_code=401, detail=user_info["error"])
        
    user_role = str(user_info.get("role", "")).upper().strip()
    if user_role in ["CEO", "ADMIN"]:
        from services.inventory_api import get_users
        users_data = await get_users()
        if users_data and users_data.get("success"):
            users_list = users_data.get("data", {}).get("users", [])
            allowed_list = []
            for u in users_list:
                first = u.get("firstName", "")
                last = u.get("lastName", "")
                fullname = f"{first} {last}".strip() or u.get("username", "")
                uname = u.get("username") or first.lower() or (u.get("email", "").split("@")[0] if "@" in u.get("email", "") else f"user_{u.get('id')}")
                dept_val = u.get("department")
                dept_name = ""
                if isinstance(dept_val, dict):
                    dept_name = dept_val.get("name", "")
                else:
                    dept_name = str(dept_val or "")
                allowed_list.append({
                    "id": u.get("id"),
                    "username": uname,
                    "name": fullname,
                    "role": u.get("role"),
                    "department": dept_name
                })
            return allowed_list
        return []

    if pr_number:
        # Fetch PR details and return only the selected approvers
        pr_data = await get_purchase_requests()
        pr_data = filter_purchase_requests(user_info, pr_data)
        
        if not pr_data or not pr_data.get("success"):
            return []
            
        prs = pr_data.get("data", {}).get("purchaseRequests", [])
        target_pr = None
        for pr in prs:
            if str(pr.get("prNumber")).lower() == pr_number.lower():
                target_pr = pr
                break
                
        if not target_pr:
            return []
            
        # Extract only approvers (exclude requester)
        approvals = target_pr.get("approvals", []) or []
        approvers_list = []
        for app in approvals:
            if isinstance(app, dict):
                approver = app.get("approver")
                if isinstance(approver, dict) and approver.get("id"):
                    first = approver.get("firstName", "")
                    last = approver.get("lastName", "")
                    fullname = f"{first} {last}".strip() or approver.get("username", "")
                    uname = approver.get("username") or first.lower() or (approver.get("email", "").split("@")[0] if "@" in approver.get("email", "") else f"user_{approver.get('id')}")
                    
                    # Resolve department name
                    dept_val = approver.get("department")
                    dept_name = ""
                    if isinstance(dept_val, dict):
                        dept_name = dept_val.get("name", "")
                    else:
                        dept_name = str(dept_val or "")
                        
                    # Prevent duplicate entries
                    if not any(u["id"] == approver.get("id") for u in approvers_list):
                        approvers_list.append({
                            "id": approver.get("id"),
                            "username": uname,
                            "name": fullname,
                            "role": "Approver",
                            "department": dept_name
                        })
        return approvers_list
        
    if user_role == "MANAGER":
        from services.inventory_api import get_users
        users_data = await get_users()
        if users_data and users_data.get("success"):
            users_list = users_data.get("data", {}).get("users", [])
            mgr_id = user_info.get("id") or user_info.get("user_id")
            
            allowed_list = []
            for u in users_list:
                u_manager_id = u.get("managerId") or u.get("manager_id") or (u.get("manager", {}).get("id") if isinstance(u.get("manager"), dict) else None)
                if u_manager_id == mgr_id:
                    first = u.get("firstName", "")
                    last = u.get("lastName", "")
                    fullname = f"{first} {last}".strip() or u.get("username", "")
                    uname = u.get("username") or first.lower() or (u.get("email", "").split("@")[0] if "@" in u.get("email", "") else f"user_{u.get('id')}")
                    
                    dept_val = u.get("department")
                    dept_name = ""
                    if isinstance(dept_val, dict):
                        dept_name = dept_val.get("name", "")
                    else:
                        dept_name = str(dept_val or "")
                        
                    allowed_list.append({
                        "id": u.get("id"),
                        "username": uname,
                        "name": fullname,
                        "role": u.get("role"),
                        "department": dept_name
                    })
            return allowed_list
        return []

    manager_id = user_info.get("managerId")
    if not manager_id:
        return []
        
    manager_profile = await resolve_user_profile(manager_id, None, None)
    if manager_profile:
        first = manager_profile.get("firstName", "")
        last = manager_profile.get("lastName", "")
        fullname = f"{first} {last}".strip() or manager_profile.get("username", "")
        uname = manager_profile.get("username") or first.lower() or (manager_profile.get("email", "").split("@")[0] if "@" in manager_profile.get("email", "") else f"user_{manager_profile.get('id')}")
        
        return [{
            "id": manager_profile.get("id"),
            "username": uname,
            "name": fullname
        }]
        
    return []

def get_associated_users_from_pr(pr: dict) -> list:
    """
    Parses the requester and all approvals history from a Purchase Request to find
    associated users dynamically from the real API response data structure.
    """
    users = []
    
    # 1. Requester
    req = pr.get("requester")
    if isinstance(req, dict) and req.get("id"):
        fullname = f"{req.get('firstName', '')} {req.get('lastName', '')}".strip() or req.get("username", "")
        users.append({
            "id": req.get("id"),
            "username": req.get("username"),
            "name": fullname,
            "role": "Requester"
        })
        
    # 2. Approver details inside the approvals list
    approvals = pr.get("approvals", []) or []
    for app in approvals:
        if isinstance(app, dict):
            approver = app.get("approver")
            if isinstance(approver, dict) and approver.get("id"):
                fullname = f"{approver.get('firstName', '')} {approver.get('lastName', '')}".strip() or approver.get("username", "")
                
                # Check for duplicate IDs
                if not any(u["id"] == approver.get("id") for u in users):
                    users.append({
                        "id": approver.get("id"),
                        "username": approver.get("username"),
                        "name": fullname,
                        "role": f"Approver"
                    })
    return users

@app.get("/api/entities/purchase-requests")
async def get_allowed_prs(authorization: str = Header(None)):
    """
    Queries the Purchase Request API, filters by user permission/scope,
    and returns allowed PRs for autocomplete dropdown options.
    """
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    else:
        token = settings.INVENTORY_ACCESS_TOKEN
        
    user_info = await verify_and_get_user(token)
    if "error" in user_info:
        raise HTTPException(status_code=401, detail=user_info["error"])
        
    # Fetch from API
    pr_data = await get_purchase_requests()
    
    # Apply backend authorization & scope filters
    pr_data = filter_purchase_requests(user_info, pr_data)
    
    if not pr_data or not pr_data.get("success"):
        return []
        
    prs_list = pr_data.get("data", {}).get("purchaseRequests", [])
    
    # Map real details (id, prNumber, description, status, amount, and associated_users)
    return [{
        "id": pr.get("id"),
        "reference": pr.get("prNumber"),
        "description": pr.get("justification"),
        "status": pr.get("status"),
        "amount": pr.get("finalApprovedAmount") or pr.get("selectedQuotePrice") or pr.get("totalAmount") or pr.get("quotePrice"),
        "associated_users": get_associated_users_from_pr(pr)
    } for pr in prs_list]

@app.get("/api/entities/invoices")
async def get_allowed_invoices(authorization: str = Header(None)):
    """
    Queries the Invoices API, filters by user permission/scope,
    and returns allowed invoices for autocomplete.
    """
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    else:
        token = settings.INVENTORY_ACCESS_TOKEN
        
    user_info = await verify_and_get_user(token)
    if "error" in user_info:
        raise HTTPException(status_code=401, detail=user_info["error"])
        
    # Fetch from API
    invoice_data = await get_invoices()
    
    # Apply backend scoping
    invoice_data = filter_invoices(user_info, invoice_data)
    
    if not invoice_data or not invoice_data.get("success"):
        return []
        
    invoice_list = invoice_data.get("data", {}).get("invoices", [])
    if not invoice_list:
        return []
    
    return [{
        "id": inv.get("id"),
        "reference": inv.get("invoiceNumber"),
        "supplier": inv.get("supplierName") or inv.get("supplier", {}).get("name"),
        "amount": inv.get("amount") or inv.get("totalAmount"),
        "status": inv.get("status")
    } for inv in invoice_list]

@app.get("/api/entities/purchase-orders")
async def get_allowed_pos(authorization: str = Header(None)):
    """
    Queries the Purchase Orders API, filters by user permission/scope,
    and returns allowed POs for autocomplete.
    """
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    else:
        token = settings.INVENTORY_ACCESS_TOKEN
        
    user_info = await verify_and_get_user(token)
    if "error" in user_info:
        raise HTTPException(status_code=401, detail=user_info["error"])
        
    # Fetch from API
    po_data = await get_purchase_orders()
    
    # Apply backend scoping
    po_data = filter_purchase_orders(user_info, po_data)
    
    if not po_data or not po_data.get("success"):
        return []
        
    po_list = po_data.get("data", {}).get("purchaseOrders", [])
    if not po_list:
        return []
    
    return [{
        "id": po.get("id"),
        "reference": po.get("poNumber"),
        "supplier": po.get("supplierName") or po.get("supplier", {}).get("name"),
        "amount": po.get("amount") or po.get("totalAmount"),
        "status": po.get("status")
    } for po in po_list]

@app.get("/api/entities/assets")
async def get_allowed_assets(authorization: str = Header(None)):
    """
    Queries the Assets API, filters by user permission/scope,
    and returns allowed assets for autocomplete.
    """
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
    else:
        token = settings.INVENTORY_ACCESS_TOKEN
        
    user_info = await verify_and_get_user(token)
    if "error" in user_info:
        raise HTTPException(status_code=401, detail=user_info["error"])
        
    # Fetch from API
    asset_data = await get_assets()
    
    # Apply backend scoping
    asset_data = filter_employee_assets(user_info, asset_data)
    
    if not asset_data or not asset_data.get("success"):
        return []
        
    asset_list = asset_data.get("data", {}).get("assets", [])
    if not asset_list:
        return []
    
    return [{
        "id": asset.get("id"),
        "reference": asset.get("assets_code"),
        "description": asset.get("assets_type") or f"{asset.get('brand', '')} {asset.get('model', '')}".strip(),
        "brand": asset.get("brand"),
        "model": asset.get("model"),
        "status": asset.get("status"),
        "location": asset.get("station_name") or asset.get("location")
    } for asset in asset_list]

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}
