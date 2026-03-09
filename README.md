# 📂 DocTracker — Flask Document Tracker

A smart document receiving & releasing tracker with **AI-powered scanning**.

## Features
- ✅ Add, view, edit, delete documents
- ✅ **📷 AI Document Scanner** — upload image or PDF, AI auto-fills the form
- ✅ Track sender & recipient details
- ✅ Date received & date released
- ✅ Status tracking (Pending, In Review, Released, On Hold, Archived)
- ✅ Search & filter by status / type
- ✅ Data saved to `documents.json` (persists between sessions)
- ✅ Dashboard with live stats

---

## Setup & Run

### 1. Install Python (3.8+)
Download from https://www.python.org/downloads/
⚠️ Check **"Add Python to PATH"** during install!

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set your Anthropic API Key (for scanning)
Get your key from https://console.anthropic.com/

**Windows:**
```cmd
set ANTHROPIC_API_KEY=sk-ant-your-key-here
```

**Mac/Linux:**
```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

> You only need the API key to use the scanner. Manual entry works without it.

### 4. Run the app
```bash
python app.py
```

### 5. Open in browser
Go to: **http://localhost:5000**

---

## File Structure
```
doctracker/
├── app.py              ← Main Flask application
├── documents.json      ← Auto-created data file
├── requirements.txt    ← Dependencies
├── README.md
└── templates/
    ├── base.html       ← Shared layout & styles
    ├── index.html      ← Document list / dashboard
    ├── detail.html     ← Single document view
    ├── form.html       ← Add / Edit form
    └── scan.html       ← AI scanner upload page
```

## API
```
GET /api/docs    → All documents as JSON
```
