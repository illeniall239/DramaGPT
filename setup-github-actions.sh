#!/bin/bash

# Setup script for GitHub Actions deployment to Google Cloud Run
# This script creates a service account and generates a key for GitHub Actions

set -e  # Exit on error

echo "🚀 Setting up GitHub Actions for Cloud Run deployment"
echo ""

# Get current project ID
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)

if [ -z "$PROJECT_ID" ]; then
    echo "❌ No GCP project is set. Please run:"
    echo "   gcloud config set project YOUR-PROJECT-ID"
    exit 1
fi

echo "📋 Current GCP Project: $PROJECT_ID"
echo ""

# Confirm with user
read -p "Is this the correct project? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Please set the correct project with: gcloud config set project YOUR-PROJECT-ID"
    exit 1
fi

echo ""
echo "Step 1: Creating service account..."
gcloud iam service-accounts create github-actions-deployer \
  --display-name="GitHub Actions Deployer" \
  --description="Service account for GitHub Actions to deploy to Cloud Run" \
  2>/dev/null || echo "Service account already exists, continuing..."

echo "✅ Service account created"
echo ""

echo "Step 2: Granting permissions..."

# Grant Cloud Run Admin role
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions-deployer@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.admin" \
  --quiet

echo "  ✓ Cloud Run Admin"

# Grant Service Account User role
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions-deployer@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser" \
  --quiet

echo "  ✓ Service Account User"

# Grant Storage Admin
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions-deployer@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/storage.admin" \
  --quiet

echo "  ✓ Storage Admin"

# Grant Artifact Registry Writer
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions-deployer@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer" \
  --quiet

echo "  ✓ Artifact Registry Writer"

echo "✅ Permissions granted"
echo ""

echo "Step 3: Generating service account key..."
gcloud iam service-accounts keys create gcp-key.json \
  --iam-account=github-actions-deployer@${PROJECT_ID}.iam.gserviceaccount.com

echo "✅ Key generated: gcp-key.json"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Setup Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📝 Next Steps:"
echo ""
echo "1. Go to your GitHub repository:"
echo "   https://github.com/illeniall239/DramaGPT/settings/secrets/actions"
echo ""
echo "2. Add these secrets:"
echo ""
echo "   GCP_SA_KEY:"
echo "   Copy the entire contents of gcp-key.json"
echo ""
echo "   GCP_PROJECT_ID:"
echo "   $PROJECT_ID"
echo ""
echo "   SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_ROLE_KEY,"
echo "   GROQ_API_KEY, GOOGLE_API_KEY:"
echo "   (Add your existing values)"
echo ""
echo "3. Push the workflow file to GitHub:"
echo "   git add .github/workflows/deploy-cloudrun.yml"
echo "   git commit -m 'Add GitHub Actions deployment'"
echo "   git push origin main"
echo ""
echo "⚠️  IMPORTANT: Delete gcp-key.json after adding to GitHub:"
echo "   rm gcp-key.json"
echo ""
echo "📖 Full instructions: GITHUB_ACTIONS_SETUP.md"
echo ""
