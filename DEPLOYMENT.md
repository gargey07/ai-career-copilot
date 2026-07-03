# Render Deployment Guide — AI Career Copilot Backend

## Overview

The backend runs as two services on Render (free tier):
1. **Web Service** — FastAPI app (`api/main.py`) serves the API + unsubscribe routes
2. **Cron Job** — Calls `POST /digest/run` every 30 minutes; pipeline handles user-level cooldowns internally

---

## 1. Deploy the Web Service

### Settings
| Field | Value |
|-------|-------|
| **Name** | `ai-career-copilot-backend` |
| **Environment** | Python 3 |
| **Root Directory** | `backend` |
| **Build Command** | `pip install -r requirements.txt && playwright install chromium` |
| **Start Command** | `uvicorn api.main:app --host 0.0.0.0 --port $PORT` |
| **Instance Type** | Free |
| **Health Check Path** | `/health` |

### Environment Variables (paste all from `backend/.env`)
Copy every variable from your `.env` file into Render → Environment → Add Secret File or individual vars.

**Critical vars:**
```
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...
GEMINI_API_KEY=...
MISTRAL_API_KEY=...
COHERE_API_KEY=...
RESEND_API_KEY=...
UNSUBSCRIBE_SECRET=<generate random 32-char string>
CRON_SECRET=<generate random 32-char string — copy to cron job too>
APP_BASE_URL=https://<your-render-service>.onrender.com
APP_ENV=production
```

> **Generate secrets:**
> ```bash
> python3 -c "import secrets; print(secrets.token_hex(32))"
> ```

---

## 2. Deploy the Cron Job (T-005)

### Settings
| Field | Value |
|-------|-------|
| **Name** | `ai-copilot-cron` |
| **Schedule** | `*/30 * * * *` *(every 30 minutes)* |
| **Command** | `curl -s -X POST https://<your-web-service>.onrender.com/digest/run -H "X-Cron-Secret: $CRON_SECRET"` |

### Environment Variables
Only needs one:
```
CRON_SECRET=<same value as the web service>
```

> **Why every 30 minutes?**
> The pipeline's 20hr cooldown (`MIN_DIGEST_GAP_HOURS=20`) ensures no user gets double-emailed.
> Running the cron every 30 min means users within different time zones get their digest at the right local time once we support `preferred_digest_time`.

---

## 3. Verify Deployment

After deploy, test:
```bash
# Health check
curl https://<your-service>.onrender.com/health

# Trigger digest manually (with secret)
curl -X POST https://<your-service>.onrender.com/digest/run \
  -H "X-Cron-Secret: your-cron-secret"

# Without secret (should return 401)
curl -X POST https://<your-service>.onrender.com/digest/run
```

Expected response from `/digest/run`:
```json
{
  "status": "accepted",
  "message": "Pipeline started in background",
  "test_mode": false,
  "triggered_at": "2026-07-03T16:00:00+00:00"
}
```

---

## 4. Frontend (Vercel)

```bash
cd frontend
vercel --prod
```

Add these to Vercel environment:
```
NEXT_PUBLIC_SUPABASE_URL=https://odnysgpixuhgozoczwpu.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
NEXT_PUBLIC_API_URL=https://<your-render-service>.onrender.com
```

---

## 5. Free Tier Limits

| Service | Limit | Notes |
|---------|-------|-------|
| Render Web | 750 hrs/month | Spins down after 15min idle |
| Render Cron | 500 runs/month | ~350 for 30-min schedule |
| Supabase | 500MB DB, 1GB Storage | Plenty for beta |
| Resend | 3,000 emails/month | ~100 users/day |
| Gemini | 200 req/day | 3rd fallback in chain |
| Mistral | ~rate limited | 4th fallback |
| Cohere | 1,000 req/month | 5th fallback |

> **Cold start note:** Free Render services spin down after 15 minutes of inactivity.
> The cron job's first request each day may take 30-60 seconds to warm up.
> This is acceptable since the digest is sent in the background anyway.
