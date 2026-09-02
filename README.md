# AI-Powered Inventory Chatbot

A separate, modular AI-powered chatbot designed specifically for the Inventory Management System. It allows users to ask natural-language questions about inventory, assets, alerts, and procurement.

## Project Architecture

```
Frontend (React/Vite) 
  ↓ (POST /api/chat)
Backend (Python FastAPI)
  ↓ (Determines Intent via LLM)
Inventory API Module
  ↓ (HTTP GET with Bearer Auth)
Real Inventory APIs (Remote)
```

The system strictly adheres to security requirements:
- **No Credentials in Frontend**: The React frontend only connects to the Python backend.
- **Backend Authentication**: The Python backend holds the `.env` `INVENTORY_ACCESS_TOKEN` and passes it securely via the `Authorization: Bearer <TOKEN>` header.
- **No Hallucinations**: The backend passes raw API JSON responses to the LLM to format the final answer. It explicitly restricts the AI from inventing business data.

## API-to-Chatbot Mapping

| User Intent | Internal Tool / Function | API Endpoint |
|-------------|-------------------------|--------------|
| "Inventory summary", "What is the current inventory?" | `get_inventory_summary()` | `GET /dashboard/inventory-summary` |
| "Where are assets located?", "Asset distribution" | `get_asset_locations()` | `GET /dashboard/assets_location` |
| "Overall summary", "Overview" | `get_dashboard_overview()` | `GET /dashboard/overview` |
| "Procurement summary", "Total procurement value" | `get_procurement_summary()` | `GET /dashboard/procurement-summary` |
| "Approved cost for 2026" | `get_monthly_approved_cost(year)` | `GET /inventory/monthly-approved-cost?year=YYYY` |
| "Show alerts", "Are there issues?" | `get_alerts()` | `GET /dashboard/alerts` |
| "What is the weather?" | `reject_out_of_scope()` | *None (Rejected)* |

## Installation & Setup

### 1. Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd inventory-chatbot/backend
   ```
2. Set up a Python environment and install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure the environment variables:
   Copy `.env.example` to `.env` and fill in your keys:
   ```env
   INVENTORY_API_BASE_URL=https://api.inventory.indianrailwayads.com/api
   INVENTORY_ACCESS_TOKEN=your_jwt_access_token
   LLM_API_KEY=your_gemini_api_key
   ```
4. Start the FastAPI server:
   ```bash
   uvicorn main:app --reload --port 8000
   ```

### 2. Frontend Setup

1. Navigate to the frontend directory:
   ```bash
   cd inventory-chatbot/frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Run the Vite development server:
   ```bash
   npm run dev
   ```
4. Open the browser to the provided localhost URL.

## Production Integration

This React component (`InventoryChatbot.jsx`) and its CSS (`index.css`) can be ported directly into the existing `inventory.indianrailwayads.com/dashboard` React application.

**Steps:**
1. Copy `InventoryChatbot.jsx` and `index.css` to your existing project.
2. Update the `BACKEND_URL` in the component to point to your deployed FastAPI backend URL.
3. Deploy the FastAPI backend to a secure server. Set the `INVENTORY_ACCESS_TOKEN` via secure environment variables. If the dashboard uses a dynamic session token, the backend should be modified to accept the token from the frontend securely (e.g., via cookies or passed headers).

## Error Handling

- The frontend gracefully shows errors if the backend is down.
- The backend gracefully handles 401, 403, 404, and 500 errors from the Inventory APIs, translating them into friendly messages (e.g., "authentication has expired").
- Out-of-scope questions are explicitly rejected.
