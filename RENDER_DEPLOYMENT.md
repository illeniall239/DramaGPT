# Deploy KB-Standalone Backend to Render

This guide walks you through deploying the KB-Standalone backend API to Render.

## Prerequisites

1. A [Render account](https://render.com) (free tier available)
2. A [Supabase project](https://supabase.com) with the database schema set up
3. API keys for:
   - Groq API (for LLM) - Get from [console.groq.com](https://console.groq.com)
   - Google Gemini API (optional) - Get from [makersuite.google.com](https://makersuite.google.com/app/apikey)

## Step 1: Set Up Supabase Database

1. Go to your Supabase project dashboard
2. Navigate to **SQL Editor**
3. Run the migration script from `database/migration.sql`
4. Run `database/verify_and_fix_rls.sql` to disable RLS for single-user mode

## Step 2: Deploy to Render

### Option A: Using render.yaml (Recommended)

1. Push your code to GitHub (already done!)
2. Go to [Render Dashboard](https://dashboard.render.com/)
3. Click **"New +"** → **"Blueprint"**
4. Connect your GitHub repository: `illeniall239/DramaGPT`
5. Render will automatically detect the `render.yaml` file
6. Click **"Apply"** to create the service

### Option B: Manual Setup

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository: `illeniall239/DramaGPT`
4. Configure the service:

   **Basic Settings:**
   - **Name**: `kb-standalone-backend`
   - **Region**: Oregon (or closest to you)
   - **Branch**: `main`
   - **Root Directory**: `backend`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`

   **Instance Type:**
   - Free tier is fine for testing

## Step 3: Set Environment Variables

In your Render service dashboard, go to **Environment** and add these variables:

### Required Variables:

```bash
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key

# LLM Configuration (use one of these)
NEXT_PUBLIC_GROQ_API_KEY=your-groq-api-key
# OR
GOOGLE_API_KEY=your-google-gemini-api-key

# Python Version
PYTHON_VERSION=3.11.0
```

### Where to Find These Values:

**Supabase Credentials:**
1. Go to your Supabase project dashboard
2. Click **Settings** → **API**
3. Copy:
   - Project URL → `SUPABASE_URL`
   - `anon` `public` key → `SUPABASE_KEY`
   - `service_role` `secret` key → `SUPABASE_SERVICE_ROLE_KEY`

**Groq API Key:**
1. Go to [console.groq.com](https://console.groq.com)
2. Create an account or sign in
3. Navigate to **API Keys**
4. Create a new API key → Copy as `NEXT_PUBLIC_GROQ_API_KEY`

**Google Gemini API Key (Optional):**
1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create or sign in to your Google account
3. Click **Get API Key** → Copy as `GOOGLE_API_KEY`

## Step 4: Deploy

1. Click **"Create Web Service"** (or **"Apply"** if using Blueprint)
2. Wait for the build to complete (5-10 minutes)
3. Once deployed, you'll get a URL like: `https://kb-standalone-backend.onrender.com`

## Step 5: Verify Deployment

Test your API by visiting:
```
https://kb-standalone-backend.onrender.com/health
```

You should see:
```json
{
  "status": "healthy",
  "service": "KB Standalone API"
}
```

## Step 6: Update Frontend Configuration

Update your frontend's API endpoint to point to your Render URL:

**In `frontend/src/config/index.ts`:**
```typescript
export const API_BASE_URL =
  process.env.NODE_ENV === 'production'
    ? 'https://kb-standalone-backend.onrender.com'
    : 'http://localhost:8000';
```

## Troubleshooting

### Build Fails

**Issue**: `ERROR: Could not find a version that satisfies the requirement...`

**Solution**: Some packages may not be available for the Python version. Check the build logs and either:
- Update the package version in `requirements.txt`
- Remove the package if not critical
- Use Python 3.11 (specified in environment variables)

### Service Crashes After Deploy

**Issue**: Service starts but crashes immediately

**Solution**: Check the logs in Render dashboard:
1. Go to your service
2. Click **Logs** tab
3. Look for error messages (usually missing environment variables)

### Timeout on First Request

**Issue**: First API call takes 30+ seconds

**Solution**: This is normal! Render's free tier spins down after inactivity. The first request wakes it up.
- Upgrade to paid tier for always-on instances
- Or accept the cold start delay

### CORS Errors

**Issue**: Frontend can't connect to backend

**Solution**: The backend already allows all origins. Make sure your frontend is using the correct API URL.

## Performance Notes

**Free Tier Limitations:**
- ⚠️ Service spins down after 15 minutes of inactivity
- ⚠️ Limited CPU and RAM
- ⚠️ 750 hours/month free (enough for one service 24/7)

**Upgrade Recommendations:**
- For production: Use **Starter** plan ($7/month) for always-on instances
- For heavy workloads: Use **Standard** plan ($25/month) for more resources

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | Yes | Your Supabase project URL |
| `SUPABASE_KEY` | Yes | Supabase anon/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Supabase service role key (secret) |
| `NEXT_PUBLIC_GROQ_API_KEY` | Yes* | Groq API key for LLM |
| `GOOGLE_API_KEY` | No | Google Gemini API key (alternative LLM) |
| `PYTHON_VERSION` | No | Python version (default: 3.11.0) |
| `PORT` | Auto | Render sets this automatically |

*Either `NEXT_PUBLIC_GROQ_API_KEY` or `GOOGLE_API_KEY` is required.

## Support

If you encounter issues:
1. Check the [Render Logs](https://render.com/docs/logs)
2. Review [Render Python Docs](https://render.com/docs/deploy-fastapi)
3. Open an issue on the GitHub repository

## Next Steps

After deploying the backend:
1. Deploy the frontend (Vercel or Render Static Site)
2. Update frontend to use production backend URL
3. Test all features end-to-end
4. Set up monitoring (Render provides basic metrics)

---

**Your Backend URL**: `https://kb-standalone-backend.onrender.com`

Test it: `curl https://kb-standalone-backend.onrender.com/health`
