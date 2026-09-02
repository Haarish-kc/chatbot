import httpx
import logging
from typing import Dict, Any, Optional
from config import settings

logger = logging.getLogger(__name__)

def get_headers() -> Dict[str, str]:
    if not settings.INVENTORY_ACCESS_TOKEN:
        raise ValueError("INVENTORY_ACCESS_TOKEN is not set in the environment settings.")
    # Safe construct without logging token
    return {
        "Authorization": f"Bearer {settings.INVENTORY_ACCESS_TOKEN}",
        "Accept": "application/json"
    }

def redact_header(headers: Dict[str, str]) -> Dict[str, str]:
    """Redact authorization token from headers for safe logging"""
    safe_headers = headers.copy()
    if "Authorization" in safe_headers:
        safe_headers["Authorization"] = "[REDACTED]"
    return safe_headers

async def make_api_request(endpoint: str) -> Dict[str, Any]:
    url = f"{settings.INVENTORY_API_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = get_headers()
    
    # Safe logging (redact headers/secrets)
    if settings.ALLOW_DEBUG_LOGGING:
        logger.debug(f"Making API GET Request to: {url} with headers {redact_header(headers)}")
        
    try:
        async with httpx.AsyncClient(timeout=settings.INVENTORY_API_TIMEOUT) as client:
            response = await client.get(url, headers=headers)
            
            if response.status_code == 401:
                return {"error": "Your Inventory session has expired. Please sign in again."}
            elif response.status_code == 403:
                return {"error": "Your account does not have permission to access this information."}
            elif response.status_code == 404:
                return {"error": "The requested Inventory information is not available."}
            elif response.status_code >= 500:
                return {"error": "The Inventory server is currently experiencing issues. Please try again later."}
                
            response.raise_for_status()
            return response.json()
            
    except httpx.TimeoutException:
        logger.error(f"Timeout connecting to Inventory API endpoint: {endpoint}")
        return {"error": "The Inventory service is taking too long to respond. Please try again."}
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error occurred: {e}")
        return {"error": "The Inventory server is currently experiencing issues. Please try again later."}
    except Exception as e:
        logger.error(f"Unexpected API request error: {e}")
        return {"error": "An unexpected error occurred while contacting the Inventory API."}

# --- Dashboard Overview Endpoints ---
async def get_dashboard_overview() -> Dict[str, Any]:
    return await make_api_request("/dashboard/overview")

async def get_quick_stats() -> Dict[str, Any]:
    return await make_api_request("/dashboard/quick-stats")

async def get_inventory_summary() -> Dict[str, Any]:
    return await make_api_request("/dashboard/inventory-summary")

async def get_alerts() -> Dict[str, Any]:
    return await make_api_request("/dashboard/alerts")

async def get_recent_assets() -> Dict[str, Any]:
    return await make_api_request("/dashboard/recent-assets")

async def get_procurement_summary() -> Dict[str, Any]:
    return await make_api_request("/dashboard/procurement-summary")

async def get_supplier_performance() -> Dict[str, Any]:
    return await make_api_request("/dashboard/supplier-performance")

async def get_department_spending() -> Dict[str, Any]:
    return await make_api_request("/dashboard/department-spending")

async def get_monthly_approved_cost(year: int) -> Dict[str, Any]:
    return await make_api_request(f"/inventory/monthly-approved-cost?year={year}")

# --- Inventory Endpoints ---
async def get_locations() -> Dict[str, Any]:
    return await make_api_request("/locations")

async def get_asset_types() -> Dict[str, Any]:
    return await make_api_request("/assetsType")

async def get_assets() -> Dict[str, Any]:
    return await make_api_request("/assets")

async def get_ho_assets() -> Dict[str, Any]:
    return await make_api_request("/hoAssets")

async def get_products() -> Dict[str, Any]:
    return await make_api_request("/inventory/items")

# --- Procurement Endpoints ---
async def get_purchase_requests() -> Dict[str, Any]:
    return await make_api_request("/procurement/purchase-requests")

async def get_workflow_status() -> Dict[str, Any]:
    return await make_api_request("/procurement/purchase-requests")

async def get_purchase_orders() -> Dict[str, Any]:
    return await make_api_request("/procurement/purchase-orders")

async def get_approval_flow_settings() -> Dict[str, Any]:
    return await make_api_request("/approval-flow-settings")

# --- Suppliers Endpoints ---
async def get_suppliers() -> Dict[str, Any]:
    return await make_api_request("/suppliers")

async def get_supplier_categories() -> Dict[str, Any]:
    return await make_api_request("/inventory/category")

async def get_procurement_cart() -> Dict[str, Any]:
    return await make_api_request("/procurement/cart")

async def get_supplier_cart() -> Dict[str, Any]:
    return await make_api_request("/procurement/supplier-cart")

async def get_supplier_kart() -> Dict[str, Any]:
    return await make_api_request("/procurement/supplier-cart")

async def get_my_cart() -> Dict[str, Any]:
    return await make_api_request("/procurement/cart")

# --- Departments Endpoints ---
async def get_departments() -> Dict[str, Any]:
    return await make_api_request("/departments")

# --- Invoices Endpoints ---
async def get_invoices() -> Dict[str, Any]:
    return await make_api_request("/procurement/invoices")

# --- Payments Endpoints ---
async def get_payments() -> Dict[str, Any]:
    return await make_api_request("/payments")

# --- Users Endpoints ---
async def get_users() -> Dict[str, Any]:
    return await make_api_request("/users")

# --- Expenses Endpoints ---
async def get_expenses() -> Dict[str, Any]:
    return await make_api_request("/expenses")

async def get_petty_cash() -> Dict[str, Any]:
    return await make_api_request("/pettycash")
