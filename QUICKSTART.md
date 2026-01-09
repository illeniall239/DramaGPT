# Quick Start Guide

## 🚀 Get Started in 3 Steps

### Step 1: Setup Database (One-time)

**⚠️ IMPORTANT: Choose Your Database Strategy**

Since you already have EDI tables in your Supabase database, you have two options:

---

**Option A: Use Existing Database (Modify Schema) - RECOMMENDED**

This modifies your existing EDI tables to work in single-user mode.

⚠️ **WARNING**: This will disable authentication on your EDI knowledge base tables. Only use this if:
- You're okay with KB being single-user in EDI too
- You want to share the same database between EDI and KB Standalone

**Steps:**
1. Go to https://supabase.com/dashboard/project/xnoxgkkwqqtzvrvppabw
2. Click "SQL Editor" → "New Query"
3. Copy and paste the entire contents of `database/modify_existing_schema.sql`
4. Click "Run" or press Ctrl+Enter
5. ✅ Done! Your existing tables are now ready for standalone mode

**What this does:**
- Removes `user_id` column from knowledge_bases
- Disables RLS on all KB tables
- Drops all user-based access policies
- Keeps all your existing KB data intact

---

**Option B: Create New Supabase Project (Clean Slate)**

This keeps EDI and KB Standalone completely separate.

**Steps:**
1. Go to https://supabase.com/dashboard
2. Click "New Project"
3. Name: "KB Standalone"
4. Choose region and password
5. Wait for project creation (~2 minutes)
6. Go to Settings → API
7. Copy new credentials:
   - Project URL
   - anon key
   - service_role key
8. Update `kb-standalone/backend/.env` with new credentials
9. Update `kb-standalone/frontend/.env` with new credentials
10. In SQL Editor, run `database/migration.sql`

---

**Verify Database Setup:**
1. In Supabase Dashboard → Table Editor
2. You should see 6 tables:
   - `knowledge_bases` (no user_id column!)
   - `kb_documents`
   - `kb_document_chunks`
   - `kb_structured_data`
   - `kb_extracted_tables`
   - `chats` (only kb_id, no workspace_id or user_id)

---

### Step 2: Install Dependencies

**Backend:**
```bash
cd kb-standalone/backend
pip install -r requirements.txt
```

**Frontend:**
```bash
cd kb-standalone/frontend
npm install
```

---

### Step 3: Run the Application

**Terminal 1 - Start Backend:**
```bash
cd kb-standalone/backend
python main.py
```
You should see: `🚀 Starting KB Standalone API on port 8000`

**Terminal 2 - Start Frontend:**
```bash
cd kb-standalone/frontend
npm run dev
```
You should see: `Ready on http://localhost:3000`

---

## ✅ Access Your Application

Open your browser and go to: **http://localhost:3000**

You should see the Knowledge Base interface with:
- "New KB" button to create your first knowledge base
- Empty state with welcome message
- No login required!

---

## 📝 First Steps After Launch

1. **Create a Knowledge Base**
   - Click "+ New KB" button
   - Enter name: "My First KB"
   - Click "Create"

2. **Upload a Document**
   - Click the upload icon (↑) next to your KB
   - Select a PDF, DOCX, or TXT file
   - Wait for processing (you'll see a progress bar)

3. **Start Chatting**
   - Click "+ New Chat" in your KB
   - Ask a question like "What is this document about?"
   - See AI-powered answers with source citations!

---

## 🔧 Troubleshooting

### Backend won't start
**Error: "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required"**
- ✅ Already configured in your `.env` file!
- Just make sure you're in the `backend/` directory when running

**Error: "No module named 'fastapi'"**
```bash
pip install -r requirements.txt
```

### Frontend won't start
**Error: "Cannot find module"**
```bash
npm install
```

**Port 3000 already in use**
```bash
# Kill existing process or use different port
npm run dev -- -p 3001
```

### Database Connection Issues
- Check Supabase project is not paused (free tier pauses after inactivity)
- Verify migration ran successfully in Supabase SQL Editor
- Check Tables exist in Supabase Dashboard → Table Editor

---

## 🎯 What's Configured

✅ **Backend `.env`:**
- Supabase URL and Service Key
- Google API Key for LLM
- Azure Speech Services (optional)
- Port 8000

✅ **Frontend `.env`:**
- Backend API URL (localhost:8000)
- Supabase URL and Anon Key
- Google API Key

✅ **Database Schema:**
- Ready to run migration script
- Optimized for single-user mode (no RLS)

---

## 📚 Next: Read the Full README.md

For complete documentation including:
- Advanced features explanation
- API endpoint reference
- Production deployment guide
- Architecture details

See: `README.md`

---

**You're all set! Just run the database migration and start the servers.** 🎉
