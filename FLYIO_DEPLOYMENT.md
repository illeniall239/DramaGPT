# Deploy KB-Standalone Backend to Fly.io

This guide will help you migrate from Render to Fly.io for better performance and reliability.

## Why Fly.io?

- ✅ **No cold starts** - Always-on, instant responses
- ✅ **Better pricing** - $1.94/month for 1GB RAM (vs Render's $7)
- ✅ **1GB RAM** - 2x more memory than Render free tier
- ✅ **Faster** - Better infrastructure and CDN
- ✅ **Reliable** - No crashes or restarts

---

## Step 1: Install Fly CLI

### Windows (PowerShell as Administrator):
```powershell
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"
```

### Mac/Linux:
```bash
curl -L https://fly.io/install.sh | sh
```

### Verify Installation:
```bash
fly version
```

---

## Step 2: Sign Up & Login

```bash
# Sign up (opens browser)
fly auth signup

# Or login if you have an account
fly auth login
```

**Note:** You'll need to add a credit card, but Fly.io won't charge you unless you exceed the free tier limits.

---

## Step 3: Deploy Your Backend

### Navigate to your project:
```bash
cd C:\Users\Hamza\EDI\kb-standalone
```

### Launch the app:
```bash
fly launch --name kb-standalone-backend --region ord
```

**What this does:**
- Detects the Dockerfile automatically
- Creates a new app named `kb-standalone-backend`
- Deploys to Chicago region (`ord`) - you can choose a different region if needed

**During setup, answer:**
- Would you like to copy configuration to the new app? **Yes**
- Would you like to set up a Postgres database? **No** (we're using Supabase)
- Would you like to set up an Upstash Redis database? **No**
- Would you like to deploy now? **No** (we need to set env vars first)

---

## Step 4: Set Environment Variables

```bash
# Supabase Configuration
fly secrets set SUPABASE_URL="https://your-project.supabase.co"
fly secrets set SUPABASE_KEY="your-supabase-anon-key"
fly secrets set SUPABASE_SERVICE_ROLE_KEY="your-service-role-key"

# LLM Configuration
fly secrets set NEXT_PUBLIC_GROQ_API_KEY="your-groq-api-key"

# Optional: Google Gemini
fly secrets set GOOGLE_API_KEY="your-google-api-key"
```

### To get your Supabase credentials:
1. Go to your Supabase project dashboard
2. **Settings** → **API**
3. Copy:
   - **Project URL** → `SUPABASE_URL`
   - **anon public** key → `SUPABASE_KEY`
   - **service_role secret** key → `SUPABASE_SERVICE_ROLE_KEY`

---

## Step 5: Deploy!

```bash
fly deploy
```

This will:
1. Build your Docker image
2. Push it to Fly.io
3. Deploy your app
4. Start the service

**Wait 2-5 minutes** for the first deployment.

---

## Step 6: Get Your New URL

```bash
fly status
```

Your app URL will be: **`https://kb-standalone-backend.fly.dev`**

Test it:
```bash
curl https://kb-standalone-backend.fly.dev/health
```

You should see:
```json
{"status":"healthy","service":"KB Standalone API"}
```

---

## Step 7: Update Frontend

### Update Vercel Environment Variable:

1. Go to your Vercel project dashboard
2. **Settings** → **Environment Variables**
3. Update `NEXT_PUBLIC_API_URL`:
   - **Old**: `https://kb-standalone-backend.onrender.com`
   - **New**: `https://kb-standalone-backend.fly.dev`
4. **Redeploy** your frontend

---

## Step 8: Monitor Your App

### View logs:
```bash
fly logs
```

### Check status:
```bash
fly status
```

### View dashboard:
```bash
fly dashboard
```

### SSH into your app (for debugging):
```bash
fly ssh console
```

---

## Fly.io Commands Cheat Sheet

```bash
# Deploy new version
fly deploy

# Scale to more instances
fly scale count 2

# Increase memory (if needed)
fly scale memory 512  # or 1024, 2048

# View environment variables
fly secrets list

# Update an environment variable
fly secrets set KEY=value

# Restart the app
fly apps restart kb-standalone-backend

# Delete the app (if needed)
fly apps destroy kb-standalone-backend
```

---

## Pricing Breakdown

### Free Tier Includes:
- **Up to 3 shared-cpu-1x VMs** with 256MB RAM each
- **160GB outbound data transfer**
- **Enough for hobby projects!**

### Paid Tier (What You're Using):
- **1GB RAM** - $1.94/month
- **Shared CPU** - Included
- **160GB transfer** - Included
- **Additional transfer** - $0.02/GB

**Total:** ~$2/month (vs Render's $7/month)

---

## Troubleshooting

### Issue 1: Build Fails

**Error**: `Cannot find requirements-render-minimal.txt`

**Solution**: Make sure you're in the project root:
```bash
cd C:\Users\Hamza\EDI\kb-standalone
```

### Issue 2: App Crashes on Start

**Check logs**:
```bash
fly logs
```

**Common cause**: Missing environment variables

**Fix**:
```bash
fly secrets list  # Check which vars are set
fly secrets set MISSING_VAR=value
```

### Issue 3: Out of Memory

**Increase memory**:
```bash
fly scale memory 2048  # 2GB
```

**Cost**: $3.88/month for 2GB

### Issue 4: Slow Deployment

**First deployment is slow** (5-10 minutes) because it builds from scratch.

**Speed up future deploys**:
- Fly caches Docker layers
- Subsequent deploys: 1-2 minutes

---

## Migrate from Render

### Step 1: Test Fly.io deployment

Make sure everything works on Fly.io first.

### Step 2: Update frontend

Change the API URL in Vercel.

### Step 3: Delete Render service

1. Go to Render dashboard
2. Select `kb-standalone-backend`
3. **Settings** → **Delete Service**

This frees up your Render free tier for other projects.

---

## Performance Comparison

| Metric | Render Free | Fly.io (1GB) |
|--------|-------------|--------------|
| Cold Start | 30-50 seconds | **None (always on)** |
| RAM | 512MB | **1GB (2x more)** |
| CPU | Shared | Shared |
| Crashes | Frequent (OOM) | **None** |
| Response Time | 200-500ms | **50-100ms** |
| Monthly Cost | $0 (but unusable) | **$1.94** |

---

## Next Steps

After successful deployment:

1. ✅ Test all features (upload, query, RAG)
2. ✅ Monitor performance for 24 hours
3. ✅ Update documentation with new URL
4. ✅ Delete Render service
5. ✅ Enjoy fast, reliable backend! 🚀

---

## Support

**Fly.io Docs**: https://fly.io/docs/
**Community**: https://community.fly.io/
**Status**: https://status.flyio.net/

**Need help?** Check the logs first:
```bash
fly logs
```

---

**Your new backend**: `https://kb-standalone-backend.fly.dev`

**Happy deploying!** 🎉
