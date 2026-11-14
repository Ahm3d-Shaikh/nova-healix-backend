# FastAPI Backend

A backend application built with **FastAPI** and Python.

## Tech Stack

- **Python** – Programming language
- **FastAPI** – Backend framework
- **Uvicorn** – ASGI server
- **Pydantic** – Data validation
- **venv** – Virtual environment

## Project Structure

```text
.
├── app/
│   ├── routers/
│   ├── services/
│   ├── models/
│   └── main.py
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Ahm3d-Shaikh/nova-healix-backend.git
cd nova-healix-backend
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
```

### 3. Activate the virtual environment

**macOS / Linux:**

```bash
source .venv/bin/activate
```

**Windows:**

```bash
.venv\Scripts\activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure environment variables

Create a `.env` file using the example:

```bash
cp .env.example .env
```

Update the environment variables as needed.

### 6. Run the development server

```bash
uvicorn app.main:app --reload
```

The API will be available at:

- **API:** http://127.0.0.1:8000
- **Swagger Documentation:** http://127.0.0.1:8000/docs
- **ReDoc:** http://127.0.0.1:8000/redoc

## Development

Make sure your virtual environment is activated before installing dependencies or running the application.

To update dependencies:

```bash
pip freeze > requirements.txt
```