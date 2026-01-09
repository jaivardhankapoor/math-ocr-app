# 🔑 Where to Get Your Credentials

## 📋 Checklist

- [ ] Copy Gemini API key (you already have this)
- [ ] Google OAuth Client ID & Secret
- [ ] Stripe Test Keys (optional - can skip for now)

---

## 1️⃣ Google OAuth (REQUIRED)

**🔗 Direct Link:** https://console.cloud.google.com/apis/credentials

### Steps:

1. **Select or create a project**
   - If you don't have one, click "Create Project"

2. **Configure OAuth consent screen** (if not done before)
   - Click "OAuth consent screen" in left sidebar
   - User Type: **External**
   - App name: `Math OCR`
   - User support email: `jkapoor.y15@gmail.com`
   - Developer contact: `jkapoor.y15@gmail.com`
   - Save and continue (skip scopes, test users)

3. **Create OAuth 2.0 Client ID**
   - Click "Credentials" in left sidebar
   - Click "+ CREATE CREDENTIALS" → "OAuth 2.0 Client ID"
   - Application type: **Web application**
   - Name: `Math OCR Local Dev`
   - Authorized redirect URIs: 
     ```
     http://localhost:3000/api/auth/callback/google
     ```
     ⚠️ **IMPORTANT:** 
     - Must be exact match (no trailing slash)
     - Must be `http://` not `https://`
     - Must be `localhost` not `127.0.0.1`

4. **Copy credentials to `.env.local`**
   - Client ID → `GOOGLE_CLIENT_ID`
   - Client secret → `GOOGLE_CLIENT_SECRET`

---

## 2️⃣ Stripe (OPTIONAL - Skip for Testing)

Since you'll have unlimited tier, Stripe is optional. Set up later when you want to test payment flow.

### If you want to set it up now:

**🔗 Stripe Dashboard:** https://dashboard.stripe.com/test

⚠️ **Make sure you're in TEST mode** (toggle in top-right corner)

### A. API Keys
**Link:** https://dashboard.stripe.com/test/apikeys

- Copy **Secret key** (starts with `sk_test_`) → `STRIPE_SECRET_KEY`
- Copy **Publishable key** (starts with `pk_test_`) → both publishable key fields

### B. Create Product
**Link:** https://dashboard.stripe.com/test/products

1. Click "+ Add product"
2. Name: `Math OCR Pro`
3. Description: `50 PDF conversions per day`
4. Add a price:
   - Standard pricing: `$9.99`
   - Recurring: Monthly
5. Save product
6. Copy **Price ID** (starts with `price_`) → `STRIPE_PRICE_ID`

### C. Webhook (for local testing, use Stripe CLI)
**Link:** https://dashboard.stripe.com/test/webhooks

For local testing, use Stripe CLI instead:
```bash
# Install Stripe CLI
brew install stripe/stripe-cli/stripe

# Login
stripe login

# Forward webhooks to localhost
stripe listen --forward-to localhost:3000/api/stripe/webhook
```

It will output a webhook secret (`whsec_...`) → use in `STRIPE_WEBHOOK_SECRET`

---

## 📝 Summary of What Goes in `.env.local`

```env
# Your existing Gemini key
GEMINI_API_KEY=AIza...

# From Google OAuth Console
GOOGLE_CLIENT_ID=123456789-abc.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-abc123...

# From Stripe (optional)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID=price_...
```

The rest is pre-configured!

---

## 🚀 After Getting Credentials

1. Fill in `.env.local` with your credentials
2. Follow `QUICKSTART.md` to start the servers
3. Sign in with Google
4. Run `python setup_mega_user.py` to get unlimited tier
5. Start converting PDFs!

---

## 🐛 Troubleshooting

### "Redirect URI mismatch"
- Check the redirect URI is **exactly**: `http://localhost:3000/api/auth/callback/google`
- Go back to Google Console and verify it's added correctly
- No typos, no trailing slash, http not https

### "Access blocked: This app's request is invalid"
- Make sure OAuth consent screen is configured
- Add your email (jkapoor.y15@gmail.com) to test users if the app is not published

### "Invalid client" error
- Double-check Client ID and Secret in `.env.local`
- Make sure there are no extra spaces or quotes
