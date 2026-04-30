# ✦ SmartTodo — AI-Powered Task Manager

A beautiful, responsive todo app with NLP (Natural Language Processing) that detects tasks, dates, locations, and priorities from plain sentences.

---

## Features

- **Smart NLP parsing** — Type a paragraph; it extracts multiple tasks automatically
- **Detects**: dates, times, locations, priorities, categories from natural language
- **Manual entry** — Full form for detailed task creation
- **Sorting**: Upcoming / Recently Added / Priority
- **Filtering**: All / Active / Done / by Category
- **List & Grid** views
- **Edit & Delete** tasks
- **Responsive** — Beautiful on mobile and desktop
- **Animations** — Smooth, modern UI

---

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python app.py
# Open http://localhost:5000
```

---

## Free Hosting on Render.com (Recommended)

1. **Push to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   gh repo create smarttodo --public --push
   # OR create a repo on github.com and push manually
   ```

2. **Deploy on Render.com**
   - Go to [render.com](https://render.com) → Sign up free
   - Click **New → Web Service**
   - Connect your GitHub repo
   - Settings:
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `gunicorn app:app`
     - **Environment**: Python 3
   - Click **Create Web Service**
   - Your app will be live at `https://smarttodo.onrender.com` in ~2 minutes!

3. **For persistent storage** (so data survives restarts):
   - In Render dashboard → **Disks** → Add Disk
   - Mount path: `/data`
   - Then change `app.py` DATABASE_URL default to: `sqlite:////data/todos.db`

---

## Free Hosting on Railway.app (Alternative)

1. Push to GitHub (same as above)
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Select your repo — it auto-detects Python and the Procfile
4. Live in seconds! Free tier: 500 hours/month

---

## Free Hosting on Fly.io (Most Reliable)

```bash
# Install flyctl: https://fly.io/docs/hands-on/install-flyctl/
fly auth signup   # free account
fly launch        # auto-configures
fly deploy
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | auto | Flask secret key |
| `DATABASE_URL` | `sqlite:///todos.db` | Database URL |
| `PORT` | `5000` | Server port |

---

## NLP Examples

Try these in the Smart Input:

```
Meet John at Starbucks downtown tomorrow at 3pm and submit the quarterly report by Friday. Also buy groceries on Saturday morning.

I need to call the dentist urgently, book flight tickets to Berlin for next week, and prepare the presentation for Monday's meeting at the office.

Pay the electricity bill today, study Python on Thursday evening, and pick up the kids from school tomorrow at 4pm.
```
