```markdown
# PoliMarket — Backend

FastAPI backend for a marketplace with users, products, chats and WebSocket-based messaging.

## Repository structure
- main.py — FastAPI app, endpoints and WebSocket chat server
- models.py — SQLModel models (User, Product, Chat, Message)
- db.py — database connection (SQLite)
- auth.py — authentication helpers (JWT)
- requirements.txt — Python dependencies
- marketplace.db — optional prepopulated SQLite DB
- static/images — uploaded images (created automatically)

## Requirements
- Python 3.10+
- pip
- (optional) Git

## Setup

1. Clone the repo
   git clone https://github.com/Jahir124/polimarket-backend.git
   cd polimarket-backend

2. Create and activate a virtual environment
   python -m venv .venv
   - macOS/Linux: source .venv/bin/activate
   - Windows (PowerShell): .\.venv\Scripts\Activate.ps1

3. Install dependencies
   pip install --upgrade pip
   pip install -r requirements.txt

4. Configure SECRET
   Edit auth.py and replace SECRET = "CHANGE_ME" with a strong secret before production.

5. Database
   The app uses SQLite (`marketplace.db`). Tables are created automatically on startup if missing.

## Run (development)
Start the server:
  uvicorn main:app --reload --host 0.0.0.0 --port 8000

Interactive API docs:
- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc

## Main endpoints

Auth
- POST /auth/register
  - Form fields: name, email, password
  - Note: email must end with `@espol.edu.ec`
  - Returns: { "id": <user_id> }

- POST /auth/login
  - OAuth2 password form (username=email, password)
  - Returns: { "access_token": "<token>", "token_type": "bearer" }

- GET /auth/me
  - Requires Authorization: Bearer <token>
  - Returns current user

Products
- GET /products — list products
- GET /products/{pid} — product details
- POST /products — create product (requires auth)
  - Form fields: title, description, price, file (upload)
  - Uploaded files saved to `static/images/` and served at `/static/images/<filename>`
  - image_url saved using BASE_URL in main.py (default http://127.0.0.1:8000)

Chats & Messages
- POST /chats/start
  - Body param: product_id (int), requires auth
  - Creates or returns chat between buyer and seller

- GET /chats/my
  - Lists chats where current user is buyer or seller

- GET /chats/{chat_id}/messages
  - Returns message history for the chat (requires membership)

WebSocket chat
- Connect to: ws://127.0.0.1:8000/ws/chats/{chat_id}?token=<access_token>
- Send JSON: { "text": "message" }
- Received broadcast includes: author_id, author_name, text, created_at

## Example usage (curl)

Register:
  curl -X POST "http://127.0.0.1:8000/auth/register" -d "name=John" -d "email=john@espol.edu.ec" -d "password=secret"

Login:
  curl -X POST "http://127.0.0.1:8000/auth/login" -d "username=john@espol.edu.ec" -d "password=secret"

Create product (replace <TOKEN> and path):
  curl -X POST "http://127.0.0.1:8000/products" -H "Authorization: Bearer <TOKEN>" -F "title=Item" -F "description=Desc" -F "price=9.99" -F "file=@/path/to/image.png"

Start chat:
  curl -X POST "http://127.0.0.1:8000/chats/start" -H "Authorization: Bearer <TOKEN>" -d "product_id=1"

WebSocket with wscat:
  wscat -c "ws://127.0.0.1:8000/ws/chats/1?token=<TOKEN>"

## Notes & recommendations
- Change SECRET before production.
- Consider moving SECRET and BASE_URL to environment variables.
- For production, use HTTPS, proper CORS, and a production-grade DB (Postgres/MySQL) instead of SQLite.
- The app enforces `@espol.edu.ec` email domain on registration.

## Resetting the database
Stop the app, remove `marketplace.db`, then restart to recreate tables (data will be lost).

## Troubleshooting
- "Token inválido" or 401: ensure you use the Bearer token from /auth/login and that SECRET hasn't been changed.
- Images not served: verify `static/images` contains the uploaded file and the saved image_url matches your BASE_URL.
```
