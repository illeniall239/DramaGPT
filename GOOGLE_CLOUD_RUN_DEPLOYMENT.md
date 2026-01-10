# Deploy KB-Standalone Backend to Google Cloud Run

This guide will help you deploy your backend to Google Cloud Run.

## Why Google Cloud Run?

- ✅ **Generous free tier** - 2 million requests/month
- ✅ **Fast cold starts** - Usually < 2 seconds
- ✅ **Up to 4GB RAM** available
- ✅ **Scales to zero** - Only pay when in use
- ✅ **Production-grade** infrastructure
- ✅ **Global CDN** for fast responses

---

## Prerequisites

- ✅ Google Cloud account created
- ✅ Credit card added (required but won't be charged on free tier)

---

## Step 1: Install Google Cloud CLI

### Windows:

1. Download the installer:
   https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe

2. Run the installer and follow the prompts

3. Restart your terminal/PowerShell

### Mac:

```bash
curl https://sdk.cloud.google.com | bash
exec -l $SHELL
```

### Verify Installation:

```bash
gcloud --version
```

---

## Step 2: Initialize & Authenticate

### Login to Google Cloud:

```bash
gcloud auth login
```

This will open your browser to sign in.

### Create a new project (or use existing):

```bash
# Create new project
gcloud projects create kb-standalone-backend --name="KB Standalone"

# Set as active project
gcloud config set project kb-standalone-backend
```

**Or list existing projects:**

```bash
gcloud projects list
gcloud config set project YOUR-PROJECT-ID
```

### Enable required APIs:

```bash
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable containerregistry.googleapis.com
```

This takes ~2 minutes.

---

## Step 3: Build & Deploy

### Navigate to your project:

```bash
cd C:\Users\Hamza\EDI\kb-standalone
```

### Deploy with one command:

```bash
gcloud run deploy kb-standalone-backend \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 10 \
  --timeout 300s \
  --port 8000
```

**What this does:**
- Builds Docker image from current directory
- Deploys to Cloud Run
- Allows public access (no authentication)
- Allocates 2GB RAM (within free tier)
- Scales to 0 when not in use (no cost!)
- 5-minute timeout for long operations

**Wait 5-10 minutes** for the first deployment (includes build time).

---

## Step 4: Set Environment Variables

After deployment, set your secrets:

```bash
# Get your service name
gcloud run services list

# Set environment variables
gcloud run services update kb-standalone-backend \
  --update-env-vars SUPABASE_URL="https://your-project.supabase.co" \
  --update-env-vars SUPABASE_KEY="your-supabase-anon-key" \
  --update-env-vars SUPABASE_SERVICE_ROLE_KEY="your-service-role-key" \
  --update-env-vars NEXT_PUBLIC_GROQ_API_KEY="your-groq-api-key" \
  --region us-central1
```

**Or set all at once:**

```bash
gcloud run services update kb-standalone-backend \
  --set-env-vars="SUPABASE_URL=https://your-project.supabase.co,SUPABASE_KEY=your-anon-key,SUPABASE_SERVICE_ROLE_KEY=your-service-role-key,NEXT_PUBLIC_GROQ_API_KEY=your-groq-key" \
  --region us-central1
```

---

## Step 5: Get Your Service URL

```bash
gcloud run services describe kb-standalone-backend --region us-central1 --format='value(status.url)'
```

Your URL will be something like:
**`https://kb-standalone-backend-RANDOM-ID-uc.a.run.app`**

### Test it:

```bash
curl https://YOUR-SERVICE-URL/health
```

Should return:
```json
{"status":"healthy","service":"KB Standalone API"}
```

---

## Step 6: Update Frontend

1. Go to your Vercel project dashboard
2. **Settings** → **Environment Variables**
3. Update `NEXT_PUBLIC_API_URL`:
   ```
   https://kb-standalone-backend-RANDOM-ID-uc.a.run.app
   ```
4. **Redeploy** your frontend

---

## Useful Commands

### View logs:
```bash
gcloud run services logs read kb-standalone-backend --region us-central1
```

### Tail logs (live):
```bash
gcloud run services logs tail kb-standalone-backend --region us-central1
```

### Get service info:
```bash
gcloud run services describe kb-standalone-backend --region us-central1
```

### Update service (redeploy):
```bash
gcloud run deploy kb-standalone-backend \
  --source . \
  --region us-central1
```

### Delete service:
```bash
gcloud run services delete kb-standalone-backend --region us-central1
```

### Check quota/billing:
```bash
gcloud billing accounts list
gcloud billing projects link kb-standalone-backend --billing-account=YOUR-BILLING-ACCOUNT
```

---

## Pricing Breakdown

### Free Tier (per month):
- **2 million requests**
- **360,000 GB-seconds** of memory
- **180,000 vCPU-seconds**
- **1 GB network egress** to North America

### What This Means:
- With 2GB RAM and 0.1s average request time:
- ~1.8 million requests/month **FREE**
- After that: $0.00002400/request (~$0.024 per 1000 requests)

**For typical usage: $0-5/month**

### Example Cost Calculator:
- 10,000 requests/day × 30 days = 300,000 requests/month
- Average 200ms response time
- 2GB RAM allocated
- **Cost: $0** (well within free tier)

---

## Optimization Tips

### 1. Reduce Memory (if needed):
```bash
gcloud run services update kb-standalone-backend \
  --memory 1Gi \
  --region us-central1
```

### 2. Keep warm (reduce cold starts):
```bash
gcloud run services update kb-standalone-backend \
  --min-instances 1 \
  --region us-central1
```

**Note:** This costs ~$7/month but eliminates cold starts

### 3. Increase concurrency (handle more requests):
```bash
gcloud run services update kb-standalone-backend \
  --concurrency 80 \
  --region us-central1
```

### 4. Add custom domain:
```bash
gcloud run domain-mappings create \
  --service kb-standalone-backend \
  --domain api.yourdomain.com \
  --region us-central1
```

---

## Monitoring & Debugging

### Cloud Console Dashboard:
```bash
gcloud run services browse kb-standalone-backend --region us-central1
```

Opens the Cloud Console for your service with:
- Request metrics
- Error rates
- CPU/Memory usage
- Logs
- Revisions

### View metrics:
```bash
# Request count
gcloud monitoring time-series list \
  --filter='metric.type="run.googleapis.com/request_count"'

# Request latency
gcloud monitoring time-series list \
  --filter='metric.type="run.googleapis.com/request_latencies"'
```

---

## Troubleshooting

### Issue 1: Build Fails

**Error**: `Cannot find requirements-render-minimal.txt`

**Solution**: Make sure Dockerfile uses correct path:
```dockerfile
COPY backend/ .
RUN pip install -r requirements-render-minimal.txt
```

### Issue 2: Service Crashes

**Check logs:**
```bash
gcloud run services logs read kb-standalone-backend --region us-central1 --limit 50
```

**Common causes:**
- Missing environment variables
- Out of memory (increase to 4GB)
- Timeout (increase from 300s to 900s)

### Issue 3: Cold Starts Too Slow

**Option A: Keep 1 instance warm**
```bash
gcloud run services update kb-standalone-backend \
  --min-instances 1 \
  --region us-central1
```

**Option B: Use Startup CPU Boost**
```bash
gcloud run services update kb-standalone-backend \
  --cpu-boost \
  --region us-central1
```

### Issue 4: 403 Forbidden

**Make sure service is public:**
```bash
gcloud run services add-iam-policy-binding kb-standalone-backend \
  --region us-central1 \
  --member="allUsers" \
  --role="roles/run.invoker"
```

---

## CI/CD with GitHub Actions (Optional)

Create `.github/workflows/deploy-cloudrun.yml`:

```yaml
name: Deploy to Cloud Run

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v2

      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v1
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}

      - name: Deploy to Cloud Run
        run: |
          gcloud run deploy kb-standalone-backend \
            --source . \
            --region us-central1 \
            --platform managed
```

---

## Comparison: Cloud Run vs Render vs Fly.io

| Feature | Cloud Run | Render Free | Fly.io |
|---------|-----------|-------------|--------|
| **Cold Starts** | ⚠️ Yes (~2s) | ❌ Yes (~30s) | ✅ No |
| **RAM** | Up to 4GB | 512MB | 256MB-1GB |
| **Free Tier** | 2M req/month | Limited hours | 3 VMs |
| **Scaling** | Automatic | Manual | Manual |
| **Cost** | Pay-per-use | $7/month | $1.94/month |
| **Best For** | Variable traffic | Quick demos | Always-on apps |

---

## Regional Deployment

Available regions (choose closest to your users):

```bash
# North America
us-central1 (Iowa)
us-east1 (South Carolina)
us-west1 (Oregon)

# Europe
europe-west1 (Belgium)
europe-west4 (Netherlands)

# Asia
asia-east1 (Taiwan)
asia-northeast1 (Tokyo)
asia-southeast1 (Singapore)

# Deploy to specific region:
gcloud run deploy kb-standalone-backend \
  --source . \
  --region europe-west1
```

---

## Next Steps

After successful deployment:

1. ✅ Test all features (upload, query, RAG)
2. ✅ Monitor performance for 24 hours
3. ✅ Set up billing alerts (optional)
4. ✅ Consider keeping 1 instance warm if cold starts are an issue
5. ✅ Update documentation with new URL

---

## Cost Monitoring

### Set up budget alerts:

```bash
# Create budget alert at $10/month
gcloud billing budgets create \
  --billing-account=YOUR-BILLING-ACCOUNT \
  --display-name="KB Backend Budget" \
  --budget-amount=10USD \
  --threshold-rule=percent=50 \
  --threshold-rule=percent=90 \
  --threshold-rule=percent=100
```

You'll get email alerts at 50%, 90%, and 100% of budget.

---

## Support

**Documentation**: https://cloud.google.com/run/docs
**Pricing**: https://cloud.google.com/run/pricing
**Status**: https://status.cloud.google.com/

**Need help?** Check logs:
```bash
gcloud run services logs tail kb-standalone-backend --region us-central1
```

---

**Your service URL**: Get it with:
```bash
gcloud run services describe kb-standalone-backend --region us-central1 --format='value(status.url)'
```

**Happy deploying!** 🚀
