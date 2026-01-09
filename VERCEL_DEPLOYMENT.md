# Deploy KB-Standalone Frontend to Vercel

This guide walks you through deploying the KB-Standalone frontend to Vercel.

## Prerequisites

1. A [Vercel account](https://vercel.com) (free tier available)
2. Your backend deployed on Render: `https://kb-standalone-backend.onrender.com`
3. Supabase project credentials

---

## Step 1: Deploy to Vercel

### Option A: Using Vercel CLI (Recommended)

1. **Install Vercel CLI**:
   ```bash
   npm install -g vercel
   ```

2. **Navigate to frontend directory**:
   ```bash
   cd frontend
   ```

3. **Login to Vercel**:
   ```bash
   vercel login
   ```

4. **Deploy**:
   ```bash
   vercel --prod
   ```

5. **Follow the prompts**:
   - Link to existing project? **No**
   - What's your project's name? **kb-standalone-frontend**
   - In which directory is your code located? **.**
   - Want to override settings? **No**

### Option B: Using Vercel Dashboard (Easier)

1. **Go to [Vercel Dashboard](https://vercel.com/dashboard)**

2. **Click "Add New..." → "Project"**

3. **Import your GitHub repository**:
   - Search for: `illeniall239/DramaGPT`
   - Click **"Import"**

4. **Configure the project**:
   - **Framework Preset**: Next.js (auto-detected)
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build` (auto-detected)
   - **Output Directory**: `.next` (auto-detected)
   - **Install Command**: `npm install` (auto-detected)

5. **Add Environment Variables** (see Step 2 below)

6. **Click "Deploy"**

---

## Step 2: Set Environment Variables

In your Vercel project settings:

1. Go to **Settings** → **Environment Variables**
2. Add these variables for **Production**:

### Required Variables:

```bash
# Backend API URL (your Render deployment)
NEXT_PUBLIC_API_URL=https://kb-standalone-backend.onrender.com

# Supabase Configuration
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-supabase-anon-key
```

### Where to Get Supabase Credentials:

1. Go to your Supabase project dashboard
2. Click **Settings** → **API**
3. Copy:
   - **Project URL** → `NEXT_PUBLIC_SUPABASE_URL`
   - **anon public key** → `NEXT_PUBLIC_SUPABASE_ANON_KEY`

---

## Step 3: Redeploy

After adding environment variables:

1. Go to **Deployments** tab
2. Click the **"..."** menu on the latest deployment
3. Click **"Redeploy"**
4. Check **"Use existing Build Cache"** for faster builds
5. Click **"Redeploy"**

---

## Step 4: Verify Deployment

1. **Get your Vercel URL**: `https://kb-standalone-frontend.vercel.app` (or custom domain)

2. **Test the app**:
   - Open the URL in your browser
   - Try creating a knowledge base
   - Upload a document
   - Make a query

3. **Check Network tab** (F12 → Network):
   - Ensure API calls go to `https://kb-standalone-backend.onrender.com`
   - Check for CORS errors (should be none since backend allows all origins)

---

## Step 5: Custom Domain (Optional)

To add a custom domain:

1. Go to **Settings** → **Domains**
2. Click **"Add"**
3. Enter your domain: `kb.yourdomain.com`
4. Follow DNS configuration instructions
5. Wait for SSL certificate (automatic, 1-2 minutes)

---

## Troubleshooting

### Issue 1: API Calls Failing

**Error**: `Failed to fetch` or `Network Error`

**Solution**:
1. Check environment variables are set correctly
2. Verify backend URL is accessible: `https://kb-standalone-backend.onrender.com/health`
3. Check browser console for CORS errors

### Issue 2: Build Fails

**Error**: `Module not found` or dependency errors

**Solution**:
```bash
# Locally test the build
cd frontend
npm install
npm run build

# If successful, push changes
git add .
git commit -m "Fix build issues"
git push origin main
```

### Issue 3: Environment Variables Not Applied

**Solution**: Redeploy after adding/changing env vars. Vercel doesn't rebuild automatically when env vars change.

### Issue 4: Slow First Load

**Solution**: This is normal! Render free tier spins down after 15 minutes of inactivity. First request wakes it up (30+ seconds). Subsequent requests are fast.

---

## Production Checklist

Before going live:

- ✅ Backend deployed and healthy: `https://kb-standalone-backend.onrender.com/health`
- ✅ Frontend deployed on Vercel
- ✅ Environment variables configured
- ✅ Supabase database schema migrated
- ✅ API calls working (test in browser)
- ✅ File upload working
- ✅ Document processing working
- ✅ Query/RAG working

---

## Performance Optimization

### For Production Use:

1. **Upgrade Render to Starter Plan** ($7/month):
   - Keeps backend always-on (no cold starts)
   - Better performance

2. **Enable Vercel Analytics**:
   - Monitor performance
   - Track errors
   - Free for hobby projects

3. **Add Caching Headers** (optional):
   - Configure in `next.config.ts`
   - Cache static assets aggressively

---

## URLs Summary

| Service | URL | Purpose |
|---------|-----|---------|
| **Backend API** | `https://kb-standalone-backend.onrender.com` | FastAPI server |
| **Health Check** | `https://kb-standalone-backend.onrender.com/health` | Verify backend is running |
| **Frontend** | `https://your-app.vercel.app` | Next.js UI |
| **Supabase** | `https://your-project.supabase.co` | Database |

---

## Support

If you encounter issues:
1. Check [Vercel Logs](https://vercel.com/docs/concepts/observability/logs)
2. Review [Next.js Deployment Docs](https://nextjs.org/docs/deployment)
3. Open an issue on GitHub

---

## Next Steps

After successful deployment:
1. Share your app URL with users
2. Monitor performance in Vercel dashboard
3. Check Render logs for backend issues
4. Set up monitoring/alerts (optional)

**Congratulations! Your KB-Standalone app is live! 🚀**
