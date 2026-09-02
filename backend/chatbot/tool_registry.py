import logging
from typing import Dict, Any, Callable

# Import services
from services.inventory_api import (
    get_dashboard_overview,
    get_quick_stats,
    get_inventory_summary,
    get_alerts,
    get_recent_assets,
    get_procurement_summary,
    get_supplier_performance,
    get_department_spending,
    get_monthly_approved_cost,
    get_locations,
    get_asset_types,
    get_assets,
    get_ho_assets,
    get_products,
    get_purchase_requests,
    get_workflow_status,
    get_purchase_orders,
    get_approval_flow_settings,
    get_suppliers,
    get_supplier_categories,
    get_procurement_cart,
    get_supplier_cart,
    get_supplier_kart,
    get_my_cart,
    get_departments,
    get_invoices,
    get_payments,
    get_users,
    get_expenses,
    get_petty_cash
)

logger = logging.getLogger(__name__)

# Map string tool names to API functions
TOOL_REGISTRY: Dict[str, Callable] = {
    # Dashboard
    "get_dashboard_overview": get_dashboard_overview,
    "get_quick_stats": get_quick_stats,
    "get_inventory_summary": get_inventory_summary,
    "get_alerts": get_alerts,
    "get_recent_assets": get_recent_assets,
    "get_procurement_summary": get_procurement_summary,
    "get_supplier_performance": get_supplier_performance,
    "get_department_spending": get_department_spending,
    "get_monthly_approved_cost": get_monthly_approved_cost,
    
    # Inventory
    "get_locations": get_locations,
    "get_asset_types": get_asset_types,
    "get_assets": get_assets,
    "get_ho_assets": get_ho_assets,
    "get_products": get_products,
    
    # Procurement
    "get_purchase_requests": get_purchase_requests,
    "get_workflow_status": get_workflow_status,
    "get_purchase_orders": get_purchase_orders,
    "get_approval_flow_settings": get_approval_flow_settings,
    
    # Suppliers
    "get_suppliers": get_suppliers,
    "get_supplier_categories": get_supplier_categories,
    "get_procurement_cart": get_procurement_cart,
    "get_supplier_cart": get_supplier_cart,
    "get_supplier_kart": get_supplier_kart,
    "get_my_cart": get_my_cart,
    
    # Departments
    "get_departments": get_departments,
    
    # Invoices
    "get_invoices": get_invoices,
    
    # Payments
    "get_payments": get_payments,
    
    # Users
    "get_users": get_users,
    
    # Expenses
    "get_expenses": get_expenses,
    "get_petty_cash": get_petty_cash
}

async def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Any:
    """
    Executes the tool by name and passes any relevant arguments.
    """
    if tool_name not in TOOL_REGISTRY:
        logger.error(f"Attempted to execute unregistered tool: {tool_name}")
        return {"error": f"Tool '{tool_name}' is not registered."}
        
    tool_func = TOOL_REGISTRY[tool_name]
    
    try:
        # Check if the tool requires specific arguments (like get_monthly_approved_cost)
        if tool_name == "get_monthly_approved_cost":
            year = int(arguments.get("year", 2026)) if arguments else 2026
            return await tool_func(year)
            
        # Standard execution for no-argument tools
        return await tool_func()
    except Exception as e:
        logger.error(f"Error executing tool '{tool_name}': {e}")
        return {"error": f"Failed to execute tool '{tool_name}' due to a backend error."}
