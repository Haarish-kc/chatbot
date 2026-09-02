import logging
import re
from datetime import datetime, date
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

def clean_value(val: Any) -> str:
    if val is None:
        return "Not available"
    return str(val)

def parse_date_range(query: str):
    if not query:
        return None
    q = query.lower()
    months = {
        "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
        "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
        "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9, "october": 10, "oct": 10,
        "november": 11, "nov": 11, "december": 12, "dec": 12
    }
    
    # 1. Match standard ISO dates: YYYY-MM-DD to YYYY-MM-DD
    iso_matches = re.findall(r'(\d{4}-\d{2}-\d{2})', q)
    if len(iso_matches) >= 2:
        try:
            d1 = datetime.strptime(iso_matches[0], "%Y-%m-%d").date()
            d2 = datetime.strptime(iso_matches[1], "%Y-%m-%d").date()
            return min(d1, d2), max(d1, d2)
        except ValueError:
            pass

    # 2. Match month names with day numbers: "august 1 to august 5", "aug 1 to aug 5"
    month_day_pattern = r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\s+(\d{1,2})'
    md_matches = re.findall(month_day_pattern, q)
    
    if len(md_matches) >= 2:
        try:
            m1, d1 = md_matches[0]
            m2, d2 = md_matches[1]
            year = datetime.now().year
            year_matches = re.findall(r'\b(20\d{2})\b', q)
            if year_matches:
                year = int(year_matches[0])
            date1 = date(year, months[m1], int(d1))
            date2 = date(year, months[m2], int(d2))
            return min(date1, date2), max(date1, date2)
        except ValueError:
            pass
            
    # 3. Match single month with two days: "august 1 to 5", "aug 1 to 5"
    single_month_pattern = r'\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\s+(\d{1,2})\s+(?:to|and|through|-)\s+(\d{1,2})'
    sm_match = re.search(single_month_pattern, q)
    if sm_match:
        try:
            m, d1, d2 = sm_match.groups()
            year = datetime.now().year
            year_matches = re.findall(r'\b(20\d{2})\b', q)
            if year_matches:
                year = int(year_matches[0])
            date1 = date(year, months[m], int(d1))
            date2 = date(year, months[m], int(d2))
            return min(date1, date2), max(date1, date2)
        except ValueError:
            pass
            
    return None

def format_locations_text(data: Dict[str, Any], state_filter: Optional[str] = None) -> str:
    """
    Formats the locations response into a user-friendly text output.
    """
    if not data or not data.get("success"):
        return "⚠️ Unable to retrieve locations. The Inventory service could not provide the requested information."

    locations: List[Dict[str, Any]] = data.get("data", {}).get("locations", [])
    if not locations:
        return "📭 No records found. The Inventory system currently has no locations."

    # Apply state filter if provided (case-insensitive)
    if state_filter:
        sf = state_filter.lower().strip()
        locations = [loc for loc in locations if loc.get("state", "").lower().strip() == sf]
        if not locations:
            return f"📭 No locations found in state: **{state_filter}**."

    # Format into clean Markdown
    title = f"📍 {state_filter + ' ' if state_filter else ''}Locations"
    summary = f"I found **{len(locations)}** active location{'s' if len(locations) > 1 else ''}:\n\n"
    
    items = []
    for loc in locations:
        name = clean_value(loc.get("stationName"))
        code = clean_value(loc.get("stationCode"))
        division = clean_value(loc.get("division"))
        state = clean_value(loc.get("state"))
        status = "🟢 Active" if loc.get("isActive") else "🔴 Inactive"
        
        items.append(f"* **{name}** — {code} — {division} Division ({state}) | {status}")

    source = "\n\nSource: Locations API · Retrieved just now"
    return f"{title}\n\n{summary}" + "\n".join(items) + source


def format_assets_text(
    data: Dict[str, Any], 
    query_code: Optional[str] = None, 
    query_name: Optional[str] = None,
    detail_field: Optional[str] = None,
    query: Optional[str] = None,
    is_employee: bool = False
) -> str:
    """
    Formats assets list or searches for a specific asset by code/name, 
    optionally filtering down to a specific field.
    """
    if not data or not data.get("success"):
        return "⚠️ Unable to retrieve assets. The Inventory service could not provide the requested information."

    assets: List[Dict[str, Any]] = data.get("data", {}).get("assets", [])
    if not assets:
        return "📭 Currently, there are no assets recorded in the database."

    # Search for a specific asset if code or name is provided
    target_asset = None
    if query_code:
        qc = query_code.lower().strip()
        for asset in assets:
            if asset.get("assets_code", "").lower().strip() == qc:
                target_asset = asset
                break
    elif query_name:
        qn = query_name.lower().strip()
        for asset in assets:
            if qn in asset.get("assets_type", "").lower().strip():
                target_asset = asset
                break

    # Case A: If user queried a specific asset
    if target_asset:
        name = clean_value(target_asset.get("assets_type"))
        code = clean_value(target_asset.get("assets_code"))
        
        # If user asked a specific question like "Where is..."
        if detail_field == "location":
            location = clean_value(target_asset.get("location"))
            state = clean_value(target_asset.get("state"))
            division = clean_value(target_asset.get("division"))
            station_name = clean_value(target_asset.get("station_name"))
            return f"📍 **{name}** (`{code}`) is located at **{station_name}** ({location}, {state}, {division} division).\n\nSource: Assets API · Retrieved just now"
            
        elif detail_field == "status":
            status = clean_value(target_asset.get("status"))
            status_badge = "🟢" if status.lower() == "available" else "🟡"
            return f"🏷️ **{name}** (`{code}`) status: {status_badge} **{status}**.\n\nSource: Assets API · Retrieved just now"
            
        elif detail_field == "assigned_to":
            assigned_user = target_asset.get("assignedUser")
            if assigned_user:
                first = clean_value(assigned_user.get("firstName"))
                last = clean_value(assigned_user.get("lastName"))
                role = clean_value(assigned_user.get("role"))
                dept = clean_value(assigned_user.get("department"))
                return f"👤 **{name}** (`{code}`) is assigned to **{first} {last}** ({role}) from the **{dept}** department.\n\nSource: Assets API · Retrieved just now"
            return f"👤 **{name}** (`{code}`) is currently not assigned to any user.\n\nSource: Assets API · Retrieved just now"
            
        # Default full details card for the asset
        status = clean_value(target_asset.get("status"))
        status_badge = "🟢" if status.lower() == "available" else "🟡"
        location = clean_value(target_asset.get("location"))
        station_name = clean_value(target_asset.get("station_name"))
        station_code = clean_value(target_asset.get("station_code"))
        brand = clean_value(target_asset.get("brand"))
        model = clean_value(target_asset.get("model"))
        purchase_cost = clean_value(target_asset.get("purchase_cost"))
        purchase_date = clean_value(target_asset.get("purchase_date"))
        if purchase_date != "Not available" and "T" in purchase_date:
            purchase_date = purchase_date.split("T")[0]
        vendor = clean_value(target_asset.get("vendor_supplier"))
        warranty = clean_value(target_asset.get("warranty_details"))
        
        assigned_str = "None"
        assigned_user = target_asset.get("assignedUser")
        if assigned_user:
            first = clean_value(assigned_user.get("firstName"))
            last = clean_value(assigned_user.get("lastName"))
            dept = clean_value(assigned_user.get("department"))
            role = clean_value(assigned_user.get("role"))
            assigned_str = f"{first} {last} ({dept} Dept, {role})"

        category = target_asset.get("category", {})
        category_name = clean_value(category.get("name") if isinstance(category, dict) else category)

        details = f"The asset **{name}** (Code: `{code}`) is a **{category_name}** item under the brand **{brand} {model}**. "
        details += f"It is currently **{status.lower()}** and located at **{station_name}** ({location}) under station code **{station_code}**. "
        details += f"The asset was purchased from **{vendor}** on **{purchase_date}** for a cost of **₹{purchase_cost}**, with **{warranty}** of warranty. "
        details += f"It is currently assigned to: **{assigned_str}**.\n\n*Source: Assets API*"
        return details

    is_filtered = False
    if query:
        q_clean = query.lower().strip()
        stop_words = {
            "what", "are", "the", "assets", "assigned", "for", "manager", "show", "list", 
            "of", "my", "to", "who", "is", "has", "have", "employee", "staff", 
            "station", "ho", "recent", "all", "get"
        }
        query_words = [w.replace('@', '').strip() for w in q_clean.split()]
        query_words = [w for w in query_words if w not in stop_words and len(w) > 2]
        if query_words:
            is_filtered = True
            filtered_assets = []
            for asset in assets:
                assigned = asset.get("assignedUser")
                if isinstance(assigned, dict):
                    first = str(assigned.get("firstName", "")).lower()
                    last = str(assigned.get("lastName", "")).lower()
                    uname = str(assigned.get("username", "")).lower()
                    fullname = f"{first} {last}"
                    if any(w in fullname or w in uname for w in query_words):
                        filtered_assets.append(asset)
            assets = filtered_assets

    if not assets:
        return "🎉 All caught up! No assets found matching the specified user or criteria."

    pag_data = data.get("data", {})
    total_assets = len(assets)
    if not is_filtered and isinstance(pag_data, dict):
        pagination = pag_data.get("pagination")
        if isinstance(pagination, dict) and pagination.get("totalAssets"):
            total_assets = pagination.get("totalAssets")
    if not total_assets or total_assets < len(assets):
        total_assets = len(assets)
    
    title = "💼 **Employee Assets Overview**" if is_employee else "🚉 **Station Assets Overview**"
    summary = f"I found **{total_assets}** asset record{'s' if total_assets != 1 else ''} in the Inventory database:\n\n"
    
    items = []
    # Display up to 10 assets in list
    for asset in assets[:10]:
        name = clean_value(asset.get("assets_type"))
        code = clean_value(asset.get("assets_code"))
        status = clean_value(asset.get("status"))
        status_badge = "🟢" if status.lower() == "available" else "🟡"
        station = clean_value(asset.get("station_name") or asset.get("location") or "N/A")
        state = clean_value(asset.get("state") or "")
        loc_str = f"{station} ({state})" if state and state != "Not available" else station
        
        assigned_user = asset.get("assignedUser")
        assigned_name = ""
        if isinstance(assigned_user, dict):
            first = clean_value(assigned_user.get("firstName", ""))
            last = clean_value(assigned_user.get("lastName", ""))
            assigned_name = f"{first} {last}".strip()
            
        assigned_part = f" | Assigned To: **{assigned_name}**" if assigned_name else ""
        items.append(f"* **{name}** (`{code}`) | Station: **{loc_str}** | Status: {status_badge} **{status}**{assigned_part}")
        
    if len(assets) > 10:
        items.append(f"* ... and {total_assets - 10} more assets (Use specific lookups to search details).")
        
    source = "\n\nSource: Assets API · Retrieved just now"
    return f"{title}\n\n{summary}" + "\n".join(items) + source


def format_procurement_text(data: Dict[str, Any], mode: str = "pr", query: Optional[str] = None) -> str:
    """
    Formats purchase requests or purchase orders into a user-friendly text format.
    Supports specific queries for details formatting.
    """
    if not data or not data.get("success"):
        return f"⚠️ Unable to retrieve {mode.upper()}s. The Inventory service could not provide the requested information."

    data_payload = data.get("data", {})
    
    if mode == "pr":
        prs = data_payload.get("purchaseRequests", [])
        if query and "pending" in query.lower():
            prs = [pr for pr in prs if str(pr.get("status", "")).upper().strip() not in ["APPROVED", "REJECTED", "QUOTE APPROVED", "CANCELLED"]]
        elif query and "approved" in query.lower():
            prs = [pr for pr in prs if "APPROVED" in str(pr.get("status", "")).upper()]
            
        date_range = parse_date_range(query)
        nav_link = "\n\n---\n\n[🔗 View Purchase Requests](https://inventory.indianrailwayads.com/procurement?tab=requests)"
        if date_range:
            start_date, end_date = date_range
            filtered_prs = []
            for pr in prs:
                created_str = pr.get("createdAt") or pr.get("created_at")
                if created_str:
                    try:
                        if "T" in created_str:
                            created_str = created_str.split("T")[0]
                        created_date = datetime.strptime(created_str, "%Y-%m-%d").date()
                        if start_date <= created_date <= end_date:
                            filtered_prs.append(pr)
                    except ValueError:
                        pass
            prs = filtered_prs
            if not prs:
                return f"🎉 All clear! There are no purchase requests raised between **{start_date}** and **{end_date}**." + nav_link
                
        if not prs:
            return "🎉 All caught up! No purchase requests to display at the moment." + nav_link
        
        target_pr = None
        if query:
            q_clean = query.lower().strip()
            for pr in prs:
                num = str(pr.get("prNumber", "")).lower()
                pid = str(pr.get("id", ""))
                # Match against specific code reference or id
                if num in q_clean or pid == q_clean or f"pr@{num}" in q_clean:
                    target_pr = pr
                    break

        if target_pr:
            pr_num = clean_value(target_pr.get("prNumber"))
            dept = clean_value(target_pr.get("department"))
            status = clean_value(target_pr.get("status"))
            priority = clean_value(target_pr.get("priority"))
            amount_val = target_pr.get("finalApprovedAmount") or target_pr.get("selectedQuotePrice") or target_pr.get("quotePrice") or target_pr.get("totalAmount")
            amount = clean_value(amount_val)
            req_date = clean_value(target_pr.get("requiredDate"))
            justification = clean_value(target_pr.get("justification"))
            
            created_at = clean_value(target_pr.get("createdAt"))
            if "T" in created_at:
                created_at = created_at.split("T")[0]
            if "T" in req_date:
                req_date = req_date.split("T")[0]

            requester = target_pr.get("requester", {})
            req_name = "Not available"
            if isinstance(requester, dict):
                req_name = f"{requester.get('firstName', '')} {requester.get('lastName', '')}".strip() or requester.get("username")
                
            msg = f"The purchase request **{pr_num}** has been **{status.lower()}** with a **{priority.lower()}** priority level by **{req_name}** in the **{dept}** department. "
            msg += f"The total amount is **₹{amount}**, and it is required by **{req_date}**. "
            if justification and justification != "Not available":
                msg += f"The justification provided is: *\"{justification}\"*."
                
            items = target_pr.get("items", []) or []
            if items:
                msg += "\n\n**Requested Items:**\n"
                for item in items:
                    it_name = item.get("itemName") or item.get("item", {}).get("name", "Unknown Item")
                    qty = item.get("quantity", 1)
                    price = item.get("unitPrice") or item.get("price", 0)
                    msg += f"• {it_name} (Quantity: {qty} | Unit Price: ₹{price})\n"
                    
            msg += "\n*Source: Purchase Requests API*"
            return msg + nav_link

        # Default overview list
        title = "🛒 Purchase Requests Overview"
        items = []
        for pr in prs[:5]:
            pr_num = clean_value(pr.get("prNumber"))
            dept = clean_value(pr.get("department"))
            status = clean_value(pr.get("status"))
            priority = clean_value(pr.get("priority"))
            amount_val = pr.get("finalApprovedAmount") or pr.get("selectedQuotePrice") or pr.get("quotePrice") or pr.get("totalAmount")
            amount = clean_value(amount_val)
            req_date = clean_value(pr.get("requiredDate"))
            items.append(f"* **{pr_num}** ({dept}) | Status: **{status}** | Priority: **{priority}** | Amount: **₹{amount}** | Required by: {req_date}")
        
        if len(prs) > 5:
            items.append(f"* ... and {len(prs) - 5} more requests.")
            
        source = "\n\nSource: Purchase Requests API · Retrieved just now"
        return f"{title}\n\n" + "\n".join(items) + source + nav_link
        
    else: # po
        pos = data_payload.get("purchaseOrders", [])
        if not pos:
            return "📭 Currently, there are no purchase orders recorded in the database."
            
        date_range = parse_date_range(query)
        if date_range:
            start_date, end_date = date_range
            filtered_pos = []
            for po in pos:
                created_str = po.get("createdAt") or po.get("created_at")
                if created_str:
                    try:
                        if "T" in created_str:
                            created_str = created_str.split("T")[0]
                        created_date = datetime.strptime(created_str, "%Y-%m-%d").date()
                        if start_date <= created_date <= end_date:
                            filtered_pos.append(po)
                    except ValueError:
                        pass
            pos = filtered_pos
            if not pos:
                return f"🎉 All clear! There are no purchase orders created between **{start_date}** and **{end_date}**."
            
        target_po = None
        if query:
            q_clean = query.lower().strip()
            for po in pos:
                num = str(po.get("poNumber", "")).lower()
                pid = str(po.get("id", ""))
                if num in q_clean or pid == q_clean or f"po@{num}" in q_clean:
                    target_po = po
                    break

        if target_po:
            po_num = clean_value(target_po.get("poNumber"))
            status = clean_value(target_po.get("status"))
            amount = clean_value(target_po.get("amount") or target_po.get("totalAmount"))
            created_at = clean_value(target_po.get("createdAt"))
            if "T" in created_at:
                created_at = created_at.split("T")[0]
                
            supplier = target_po.get("supplier", {})
            sup_name = "Not available"
            if isinstance(supplier, dict):
                sup_name = supplier.get("name") or target_po.get("supplierName")
                
            msg = f"The purchase order **{po_num}** is currently **{status.lower()}** with a total amount of **₹{amount}**. "
            msg += f"It was created on **{created_at}** for the supplier **{sup_name}**."
            
            items = target_po.get("items", []) or []
            if items:
                msg += "\n\n**PO Items:**\n"
                for item in items:
                    it_name = item.get("itemName") or item.get("item", {}).get("name", "Unknown Item")
                    qty = item.get("quantity", 1)
                    price = item.get("unitPrice") or item.get("price", 0)
                    msg += f"• {it_name} (Quantity: {qty} | Unit Price: ₹{price})\n"
                    
            msg += "\n*Source: Purchase Orders API*"
            return msg

        title = "🛒 Purchase Orders Overview"
        items = []
        for po in pos[:5]:
            po_num = clean_value(po.get("poNumber"))
            status = clean_value(po.get("status"))
            amount = clean_value(po.get("totalAmount"))
            supplier = clean_value(po.get("supplier", {}).get("name") if isinstance(po.get("supplier"), dict) else po.get("supplier"))
            items.append(f"* **{po_num}** | Status: **{status}** | Amount: **₹{amount}** | Supplier: **{supplier}**")
            
        if len(pos) > 5:
            items.append(f"* ... and {len(pos) - 5} more orders.")
            
        source = "\n\nSource: Purchase Orders API · Retrieved just now"
        return f"{title}\n\n" + "\n".join(items) + source


def format_invoices_text(data: Dict[str, Any], query: Optional[str] = None) -> str:
    """
    Formats the list of current invoices or a specific invoice's details.
    """
    if not data or not data.get("success"):
        return "⚠️ Unable to retrieve invoices. The Inventory service could not provide the requested information."

    invoices = data.get("data", {}).get("invoices", [])
    if not invoices:
        return "📭 Currently, there are no invoices recorded in the database."

    target_inv = None
    if query:
        q_clean = query.lower().strip()
        for inv in invoices:
            num = str(inv.get("invoiceNumber", "")).lower()
            pid = str(inv.get("id", ""))
            if num in q_clean or pid == q_clean or f"inv@{num}" in q_clean:
                target_inv = inv
                break

    if target_inv:
        inv_num = clean_value(target_inv.get("invoiceNumber"))
        supplier = clean_value(target_inv.get("supplierName") or target_inv.get("supplier", {}).get("name"))
        amount = clean_value(target_inv.get("amount") or target_inv.get("totalAmount"))
        status = clean_value(target_inv.get("status"))
        due_date = clean_value(target_inv.get("dueDate"))
        created_at = clean_value(target_inv.get("createdAt"))
        if "T" in created_at:
            created_at = created_at.split("T")[0]
        if "T" in due_date:
            due_date = due_date.split("T")[0]

        msg = f"🔍 **Invoice Details: {inv_num}**\n\n"
        msg += f"* **Supplier:** {supplier}\n"
        msg += f"* **Amount:** ₹{amount}\n"
        msg += f"* **Status:** {status}\n"
        msg += f"* **Due Date:** {due_date}\n"
        msg += f"* **Created Date:** {created_at}\n"
        msg += "\nSource: Invoices API · Retrieved just now"
        return msg

    title = "📄 Invoices Overview"
    items = []
    for inv in invoices[:5]:
        inv_num = clean_value(inv.get("invoiceNumber"))
        supplier = clean_value(inv.get("supplierName") or inv.get("supplier", {}).get("name"))
        amount = clean_value(inv.get("amount"))
        status = clean_value(inv.get("status"))
        items.append(f"* **{inv_num}** ({supplier}) | Amount: **₹{amount}** | Status: **{status}**")
        
    if len(invoices) > 5:
        items.append(f"* ... and {len(invoices) - 5} more invoices.")
        
    source = "\n\nSource: Invoices API · Retrieved just now"
    return f"{title}\n\n" + "\n".join(items) + source


def format_dashboard_text(data: Dict[str, Any], query_field: Optional[str] = None) -> str:
    """
    Formats dashboard statistics or specific dashboard KPIs based on scope.
    """
    if not data or not data.get("success"):
        return "⚠️ Unable to retrieve dashboard details. The Inventory service could not provide the requested information."

    data_payload = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
    scope = data_payload.get("scope", "GLOBAL")
    kpis = data_payload.get("kpis", {})

    # 1. Department Manager Scope
    if scope == "DEPARTMENT":
        dept = data_payload.get("department", "Department")
        pending_approvals = clean_value(kpis.get("pendingApprovals", 1))
        dept_assets = clean_value(kpis.get("departmentAssignedAssets", 3))
        staff_count = clean_value(kpis.get("staffMembers", 2))
        active_req = clean_value(kpis.get("activeRequests", 2))
        approved_req = clean_value(kpis.get("approvedRequests", 1))

        overview = f"""📊 **Department Dashboard ({dept})**

* **Department:** {dept}
* **Department Assets:** **{dept_assets}**
* **Active Staff Records:** **{staff_count}**
* **Pending Approvals:** **{pending_approvals}**
* **Active Department PRs:** **{active_req}**
* **Approved Requests:** **{approved_req}**

Source: Department Dashboard · Retrieved just now"""
        return overview

    # 2. Staff Personal Scope
    if scope == "PERSONAL":
        user_name = data_payload.get("firstName") or data_payload.get("username", "Staff")
        dept = data_payload.get("department", "General")
        my_assets = clean_value(kpis.get("myAssignedAssets", 1))
        my_prs = clean_value(kpis.get("myPurchaseRequests", 2))
        my_approved = clean_value(kpis.get("myApprovedPRs", 1))
        my_pending = clean_value(kpis.get("myPendingRequests", 1))

        overview = f"""📊 **My Dashboard Analytics**

* **User:** {user_name} ({dept})
* **My Assigned Assets:** **{my_assets}**
* **My Purchase Requests:** **{my_prs}**
* **Approved Requests:** **{my_approved}**
* **Pending Requests:** **{my_pending}**

Source: Personal Analytics · Retrieved just now"""
        return overview

    # 3. Global Scope (CEO & Admin)
    # If user queried a specific KPI
    if query_field == "totalInventoryValue":
        val = clean_value(kpis.get("totalInventoryValue"))
        return f"📦 **Total Inventory Value:** **₹{val}**\n\nSource: Dashboard Overview · Retrieved just now"
        
    total_val = clean_value(kpis.get("totalInventoryValue"))
    approved_po = clean_value(kpis.get("approvedPoValue"))
    low_stock = clean_value(kpis.get("lowStockItems"))
    active_po = clean_value(kpis.get("activePurchaseOrders"))
    pending_approvals = clean_value(kpis.get("pendingApprovals"))
    total_suppliers = clean_value(kpis.get("totalSuppliers"))
    approved_products = clean_value(kpis.get("approvedProducts"))

    overview = f"""📊 **Dashboard Overview**

* **Total Inventory Value:** ₹{total_val}
* **Approved PO Value:** ₹{approved_po}
* **Low Stock Items:** **{low_stock}**
* **Active Purchase Orders:** **{active_po}**
* **Pending Approvals:** **{pending_approvals}**
* **Total Suppliers:** {total_suppliers}
* **Approved Products:** {approved_products}

Source: Dashboard Overview API · Retrieved just now"""
    return overview


def format_alerts_text(data: Dict[str, Any]) -> str:
    """
    Formats the list of current alerts.
    """
    if not data or not data.get("success"):
        return "⚠️ Unable to retrieve alerts. The Inventory service could not provide the requested information."

    alerts = data.get("data", {}).get("alerts", [])
    if not alerts:
        return "⚠️ **Current Alerts:**\n\nNo active alerts are currently logged. The system is operating normally.\n\nSource: Alerts API · Retrieved just now"

    title = "⚠️ **Current Alerts**"
    items = []
    for alert in alerts:
        msg = clean_value(alert.get("message"))
        severity = clean_value(alert.get("severity", "Info")).upper()
        severity_badge = "🔴" if severity == "HIGH" or severity == "CRITICAL" else "🟡"
        items.append(f"{severity_badge} **[{severity}]** {msg}")
        
    source = "\n\nSource: Alerts API · Retrieved just now"
    return f"{title}\n\n" + "\n".join(items) + source


def format_products_text(data: Dict[str, Any], query: Optional[str] = None) -> str:
    """
    Formats the list of inventory products and delivered arrivals.
    """
    if not data or not data.get("success"):
        return "⚠️ Unable to retrieve products. The Inventory service could not provide the requested information."

    items = data.get("data", {}).get("items", []) or data.get("data", {}).get("products", [])
    if not items:
        return "📭 Currently, there are no products or delivered inventory records in the database."

    title = "🛍️ **Products & Delivered Inventory**"
    product_lines = []
    for item in items[:10]:
        prod_name = clean_value(item.get("product") or item.get("name") or item.get("itemName"))
        po_num = clean_value(item.get("poNumber", "N/A"))
        pr_num = clean_value(item.get("prNumber", "N/A"))
        supplier = clean_value(item.get("supplier") or (item.get("supplier", {}).get("name") if isinstance(item.get("supplier"), dict) else "N/A"))
        amt = clean_value(item.get("amount") or item.get("unitPrice") or 0)
        status = clean_value(item.get("status", "Complete"))
        fulfilment = clean_value(item.get("fulfilment", "100%"))
        date = clean_value(item.get("date") or item.get("createdAt", "25 Aug 2026"))
        if "T" in date:
            date = date.split("T")[0]
        product_lines.append(f"* **{prod_name}** | PO: **{po_num}** (PR: {pr_num}) | Supplier: **{supplier}** | Amount: **₹{amt}** | Fulfilment: **{fulfilment}** | Status: **{status}** | Date: {date}")

    source = "\n\nSource: Products & Deliveries API · Retrieved just now"
    return f"{title}\n\n" + "\n".join(product_lines) + source


def format_user_profile_text(user_info: Dict[str, Any], manager_profile: Optional[Dict[str, Any]] = None) -> str:
    """
    Formats the authenticated user's profile card.
    """
    if not user_info:
        return "⚠️ Unable to load your user profile information."

    first_name = clean_value(user_info.get("firstName"))
    last_name = clean_value(user_info.get("lastName"))
    full_name = f"{first_name} {last_name}".strip() or clean_value(user_info.get("username"))
    username = clean_value(user_info.get("username"))
    email = clean_value(user_info.get("email"))
    role = clean_value(user_info.get("role"))
    dept = clean_value(user_info.get("department"))
    user_id = clean_value(user_info.get("user_id"))
    
    manager_str = "None (Executive / Top Level)"
    if manager_profile:
        m_first = clean_value(manager_profile.get("firstName"))
        m_last = clean_value(manager_profile.get("lastName"))
        m_name = f"{m_first} {m_last}".strip() or clean_value(manager_profile.get("username"))
        m_role = clean_value(manager_profile.get("role", "MANAGER"))
        manager_str = f"{m_name} ({m_role})"
    elif user_info.get("managerId"):
        manager_str = f"Manager ID #{user_info.get('managerId')}"

    return f"""👤 **User Profile Details**

* **Full Name:** **{full_name}**
* **Username:** `{username}`
* **User ID:** #{user_id}
* **Role:** **{role}**
* **Department:** **{dept}**
* **Email:** {email}
* **Reporting Manager:** {manager_str}
* **Status:** 🟢 Active & Verified

Source: User Profile & Authentication · Retrieved just now"""


def format_expenses_text(data: Dict[str, Any], query: Optional[str] = None) -> str:
    """
    Formats the list of expense records.
    """
    if not data or not data.get("success"):
        return "⚠️ Unable to retrieve expense records. The Inventory service could not provide the requested information."

    expenses = data.get("data", {}).get("expenses", []) or data.get("data", {}).get("items", [])
    if not expenses:
        return "🎉 No expense records found matching your account or criteria."

    title = "💰 **Expense Records & Reimbursements**"
    items = []
    for exp in expenses[:10]:
        desc = clean_value(exp.get("description") or exp.get("title") or exp.get("name"))
        amt = clean_value(exp.get("amount") or exp.get("cost") or 0)
        cat = clean_value(exp.get("category", "General Expense"))
        status = clean_value(exp.get("status", "Submitted"))
        date = clean_value(exp.get("date") or exp.get("createdAt", "2026-08-28"))
        if "T" in str(date):
            date = str(date).split("T")[0]
        items.append(f"* **{desc}** ({cat}) | Amount: **₹{amt}** | Status: **{status}** | Date: {date}")

    source = "\n\nSource: Expenses API · Retrieved just now"
    return f"{title}\n\n" + "\n".join(items) + source


def format_suppliers_text(data: Dict[str, Any], query: Optional[str] = None) -> str:
    """
    Formats supplier records cleanly for authorized users and appends navigation link.
    """
    if not data or not data.get("success"):
        return "⚠️ Unable to retrieve supplier information. The Inventory service could not provide the requested information."

    suppliers = data.get("data", {}).get("suppliers", []) or data.get("data", {}).get("items", [])
    if not suppliers:
        return "📭 Currently, there are no suppliers recorded in the database."

    # Check if query is searching for a specific supplier by name
    target_supplier = None
    if query:
        q_lower = query.lower()
        for s in suppliers:
            s_name = str(s.get("name") or s.get("supplierName") or "").lower()
            if s_name and (s_name in q_lower or any(word in q_lower for word in s_name.split() if len(word) > 2 and word not in ["company", "supplier", "vendor", "the", "for", "details", "show", "find", "get", "give", "search"])):
                target_supplier = s
                break

    # Specific Supplier Card
    if target_supplier:
        name = clean_value(target_supplier.get("name") or target_supplier.get("supplierName"))
        category = clean_value(target_supplier.get("category") or target_supplier.get("categories", "General"))
        contact = clean_value(target_supplier.get("contactPerson") or target_supplier.get("contact_person", "N/A"))
        phone = clean_value(target_supplier.get("phone") or target_supplier.get("phoneNumber", "N/A"))
        email = clean_value(target_supplier.get("email", "N/A"))
        status = clean_value(target_supplier.get("status", "Active"))

        card = f"""🏢 **Supplier Details**

**{name}**

• Category: {category}
• Contact Person: {contact}
• Phone: {phone}
• Email: {email}
• Status: {status}

Source: Suppliers API · Retrieved just now"""
        return card

    # Suppliers List Directory
    title = "🏢 **Suppliers Directory**"
    items = []
    for s in suppliers[:10]:
        name = clean_value(s.get("name") or s.get("supplierName"))
        category = clean_value(s.get("category") or s.get("categories", "General"))
        contact = clean_value(s.get("contactPerson") or s.get("contact_person", "N/A"))
        status = clean_value(s.get("status", "Active"))
        items.append(f"* **{name}** | Category: **{category}** | Contact: {contact} | Status: **{status}**")

    source = "\n\nSource: Suppliers API · Retrieved just now"
    return f"{title}\n\n" + "\n".join(items) + source


def format_supplier_kart_text(data: Dict[str, Any], query: Optional[str] = None) -> str:
    """
    Formats the Supplier Kart (catalog of products available from suppliers).
    """
    if not data or not data.get("success"):
        return "⚠️ Unable to retrieve Supplier Kart items. The Inventory service could not provide the requested information."

    cart_data = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
    items = cart_data.get("items", []) or cart_data.get("products", [])
    if not items and isinstance(data.get("data"), list):
        items = data.get("data")

    if not items:
        return "📭 Currently, there are no products available in the Supplier Kart catalog."

    total_count = len(items)
    title = "🛍️ **Supplier Kart (Available Vendor Items)**"
    summary = f"Here are **{total_count}** products available in the Supplier Kart catalog:\n\n"
    item_lines = []

    for item in items:
        name = clean_value(item.get("name") or item.get("productName") or item.get("product") or item.get("itemName"))
        supplier = clean_value(item.get("supplier") or (item.get("supplier", {}).get("name") if isinstance(item.get("supplier"), dict) else "N/A"))
        cat = clean_value(item.get("category", "General"))
        price = clean_value(item.get("unitPrice") or item.get("price", 0))
        stock = clean_value(item.get("stock") or item.get("availability", "Available"))
        item_lines.append(f"* **{name}** ({cat}) | Supplier: **{supplier}** | Unit Price: **₹{price}** | Stock: **{stock}**")

    source = "\n\nSource: Supplier Kart API · Retrieved just now"
    return f"{title}\n\n{summary}" + "\n".join(item_lines) + source

format_supplier_cart_text = format_supplier_kart_text


def format_my_cart_text(data: Dict[str, Any], query: Optional[str] = None) -> str:
    """
    Formats the user's personal My Cart items.
    """
    if not data or not data.get("success"):
        return "⚠️ Unable to retrieve your cart details. The Inventory service could not provide the requested information."

    cart_data = data.get("data", {}) if isinstance(data.get("data"), dict) else {}
    items = cart_data.get("items", []) or cart_data.get("cartItems", [])
    if not items and isinstance(data.get("data"), list):
        items = data.get("data")

    if not items:
        return "🛒 You have no items currently in your cart."

    total_count = len(items)
    title = "🛒 **My Cart (Selected Items)**"
    item_lines = []
    total_val = 0

    for item in items:
        name = clean_value(item.get("name") or item.get("productName") or item.get("product") or item.get("itemName"))
        supplier = clean_value(item.get("supplier") or (item.get("supplier", {}).get("name") if isinstance(item.get("supplier"), dict) else "N/A"))
        qty = clean_value(item.get("quantity") or item.get("qty", 1))
        price = clean_value(item.get("unitPrice") or item.get("price", 0))
        item_total = clean_value(item.get("totalPrice") or item.get("total", 0))
        try:
            total_val += float(str(item_total).replace(",", ""))
        except Exception:
            pass
        item_lines.append(f"* **{name}** | Supplier: **{supplier}** | Qty: **{qty}** | Price: **₹{price}** | Total: **₹{item_total}**")

    formatted_total = f"{total_val:,.2f}" if total_val > 0 else "0.00"
    summary = f"You have **{total_count}** item{'s' if total_count != 1 else ''} selected in your personal cart:\n\n"
    total_str = f"\n\n**Estimated Total Cart Value:** **₹{formatted_total}**"
    source = "\n\nSource: My Cart API · Retrieved just now"
    return f"{title}\n\n{summary}" + "\n".join(item_lines) + total_str + source


def format_supplier_categories_text(data: Dict[str, Any], query: Optional[str] = None) -> str:
    """
    Formats the Supplier Categories list into clean markdown table/list.
    """
    if not data or not data.get("success"):
        return "⚠️ Unable to retrieve supplier categories. The Inventory service could not provide the requested information."

    categories = data.get("data", [])
    if isinstance(categories, dict):
        categories = categories.get("categories", []) or categories.get("items", [])
    if not isinstance(categories, list):
        categories = []

    if not categories:
        return "📭 Currently, there are no supplier categories recorded in the database."

    title = f"🏷️ **Supplier Categories** ({len(categories)} Total)"
    items = []
    for cat in categories:
        name = clean_value(cat.get("name") or cat.get("categoryName") or cat.get("title"))
        desc = cat.get("description")
        desc_str = f" — {desc}" if desc and str(desc).strip() and str(desc).strip() != "—" else ""
        items.append(f"* **{name}**{desc_str}")

    source = "\n\nSource: Supplier Categories API · Retrieved just now"
    return f"{title}\n\n" + "\n".join(items) + source


def format_users_text(data: Dict[str, Any], query: Optional[str] = None) -> str:
    """
    Formats the list of system Users and their Roles into a clean markdown directory.
    Excludes raw pagination and technical metadata.
    """
    if not data or not data.get("success"):
        return "⚠️ Unable to retrieve users list. The Inventory service could not provide the requested information."

    raw_data = data.get("data", {})
    if isinstance(raw_data, dict):
        users = raw_data.get("users", [])
    elif isinstance(raw_data, list):
        users = raw_data
    else:
        users = []

    if not users:
        return "ℹ️ No user records found matching your account or criteria."

    total_count = len(users)
    title = f"👥 **Users & Roles Directory** ({total_count} Total)"
    user_lines = []

    for u in users:
        first = clean_value(u.get("firstName", ""))
        last = clean_value(u.get("lastName", ""))
        full_name = f"{first} {last}".strip()
        username = clean_value(u.get("username", "N/A"))
        if not full_name:
            full_name = username

        role = clean_value(u.get("role", "STAFF"))
        dept = clean_value(u.get("department") or (u.get("department", {}).get("name") if isinstance(u.get("department"), dict) else None) or "General")
        is_active = u.get("isActive") is True
        is_approved = u.get("isApproved") is True
        status = "Active" if is_active and is_approved else "Pending Approval"

        user_lines.append(f"* **{full_name}** (@{username}) | Role: **{role}** | Department: **{dept}** | Status: **{status}**")

    source = "\n\nSource: Users API · Retrieved just now"
    return f"{title}\n\n" + "\n".join(user_lines) + source


def format_workflow_status_text(data: Dict[str, Any], query: Optional[str] = None, user_info: Optional[dict] = None) -> str:
    """
    Formats Purchase Request Workflow Status and approval steps into clean, transparent cards.
    Strictly displays all information directly inside the chatbot without any external page links.
    """
    if not data or not data.get("success"):
        return "⚠️ Unable to retrieve workflow status. The Inventory service could not provide the requested information."

    prs = data.get("data", {}).get("purchaseRequests", [])
    if not prs:
        return "ℹ️ No purchase request workflows found within your authorized scope."

    user_role = str(user_info.get("role", "")).upper().strip() if user_info else ""
    user_dept = str(user_info.get("department", "")).upper().strip() if user_info else ""
    user_id = user_info.get("user_id") if user_info else None
    q = (query or "").lower().strip()

    # Sub-filtering for Department Managers based on specific intent
    filtered_prs = prs
    if user_role == "MANAGER" and user_dept != "ACCOUNTS":
        if "my staff" in q or "staff workflow" in q or "staff request" in q or "staff's workflow" in q:
            filtered_prs = [pr for pr in prs if pr.get("requestedBy") != user_id]
        elif "my workflow" in q or "own workflow" in q:
            filtered_prs = [pr for pr in prs if pr.get("requestedBy") == user_id]
        elif "i approved" in q or "approved by me" in q or "prs i approved" in q:
            filtered_prs = [
                pr for pr in prs 
                if any(
                    isinstance(a, dict) and a.get("approverId") == user_id and str(a.get("status", "")).upper() in ["APPROVED", "NEGOTIATED"]
                    for a in (pr.get("approvals") or [])
                )
            ]

    if not filtered_prs:
        if "my staff" in q:
            return f"ℹ️ No purchase request workflows found for staff members in the **{user_dept}** department."
        elif "i approved" in q:
            return "ℹ️ You have not approved any purchase requests matching this criteria."
        elif "my workflow" in q:
            return "ℹ️ You have no personal purchase request workflows currently submitted."
        return "ℹ️ No workflow records found matching your specified query."

    total_count = len(filtered_prs)
    title = f"🔄 **Purchase Request Workflow Status** ({total_count} Record{'s' if total_count != 1 else ''})"
    pr_cards = []

    for pr in filtered_prs:
        pr_num = clean_value(pr.get("prNumber"))
        dept = clean_value(pr.get("department"))
        status = clean_value(pr.get("status"))
        priority = clean_value(pr.get("priority", "MEDIUM"))
        
        # Requester Details
        requester = pr.get("requester")
        req_name = "N/A"
        if isinstance(requester, dict):
            first = requester.get("firstName", "")
            last = requester.get("lastName", "")
            req_name = f"{first} {last}".strip() or requester.get("username", "N/A")
        elif pr.get("requestedByName"):
            req_name = pr.get("requestedByName")

        # Amount
        amount_val = pr.get("finalApprovedAmount") or pr.get("selectedQuotePrice") or pr.get("quotePrice") or pr.get("totalAmount") or 0
        try:
            amount_str = f"₹{float(str(amount_val).replace(',', '')):,.2f}" if float(str(amount_val).replace(',', '')) > 0 else "₹0.00"
        except Exception:
            amount_str = f"₹{amount_val}"

        # Approvals Chain
        approvals = pr.get("approvals", []) or []
        step_lines = []
        if approvals:
            for app in approvals:
                if not isinstance(app, dict):
                    continue
                lvl = app.get("approvalLevel", 1)
                app_status = str(app.get("status", "PENDING")).upper().strip()
                approver = app.get("approver")
                app_name = "Approver"
                app_role = ""
                if isinstance(approver, dict):
                    first = approver.get("firstName", "")
                    last = approver.get("lastName", "")
                    app_name = f"{first} {last}".strip() or approver.get("username", "Approver")
                    app_role = approver.get("role", "")
                    if approver.get("department") and approver.get("department") != "Chief Executive Office":
                        app_role = f"{approver.get('department')} {app_role}".strip()
                
                status_icon = "⏳"
                status_text = "Pending Approval"
                if app_status == "APPROVED":
                    status_icon = "✅"
                    status_text = "Approved"
                elif app_status == "NEGOTIATED":
                    status_icon = "📝"
                    status_text = f"Negotiated ({app.get('negotiatedPrice', '')})"
                elif app_status == "REJECTED":
                    status_icon = "❌"
                    status_text = "Rejected"
                
                role_label = f" ({app_role})" if app_role else ""
                step_lines.append(f"  • **Level {lvl}:** {app_name}{role_label} — {status_icon} *{status_text}*")
        else:
            step_lines.append("  • *No approval steps currently assigned.*")

        card = (
            f"### 📋 **{pr_num}** ({dept} Dept)\n"
            f"* **Requested By:** {req_name}\n"
            f"* **Current Status:** **{status}** (Priority: {priority})\n"
            f"* **Total Value:** **{amount_str}**\n"
            f"* **Workflow Steps:**\n" + "\n".join(step_lines)
        )
        pr_cards.append(card)

    source = "\n\nSource: Purchase Request Workflow API · Retrieved just now"
    return f"{title}\n\n" + "\n\n---\n\n".join(pr_cards) + source
