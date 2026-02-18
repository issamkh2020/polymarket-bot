# ☁️ Run the Bot 24/7 for FREE — GitHub Actions Guide

> **No credit card. No server. Just a free GitHub account.**
> GitHub runs your bot every 15 minutes automatically, forever.

---

## How it works (simple version)

GitHub is a free website where developers store code.
It has a feature called **Actions** that can automatically run code on a schedule.
We use it like a free alarm clock: every 15 minutes, GitHub wakes up, runs your bot,
the bot scans Polymarket and places orders if found, then goes back to sleep.

**Your PC can be completely off. It's all in the cloud. It's all free.**

---

## What you need

- ✅ A free GitHub account (just an email, no credit card)
- ✅ Your Polymarket API credentials
- ✅ Your MetaMask private key

That's it.

---

## Step 1 — Create a GitHub account

1. Go to **https://github.com**
2. Click **Sign up**
3. Enter your email, create a password, pick a username
4. Verify your email

---

## Step 2 — Create a new repository (where your bot code lives)

1. After logging in, click the **+** button (top right) → **New repository**
2. Fill in:
   - **Repository name:** `polymarket-bot` (or anything you like)
   - **Visibility:** Select **Public** ✅
     *(Don't worry — your secrets like private key are stored separately and are never visible)*
   - Leave everything else as default
3. Click **Create repository**

You'll see an empty repository page.

---

## Step 3 — Upload the bot files

1. On your repository page, click **uploading an existing file** (or drag and drop)
2. Drag ALL the files from the `polymarket_bot_v2` folder into the upload area:
   - `bot.py`
   - `requirements.txt`
   - The `.github` folder *(this is important — it contains the schedule)*

   ⚠️ **Make sure to upload the `.github` folder and everything inside it.**
   On Mac, hidden folders (starting with `.`) might not show. To see them:
   - Press `Cmd + Shift + .` in Finder to toggle hidden files

3. Scroll down, click **Commit changes**

Your files are now on GitHub.

---

## Step 4 — Add your secrets (private key, API credentials)

Your sensitive credentials are stored in GitHub **Secrets** — they are encrypted,
invisible to everyone including you after saving, and only injected into the bot at runtime.

1. Go to your repository page
2. Click **Settings** (top tab)
3. In the left sidebar: **Secrets and variables** → **Actions**
4. Click **New repository secret** for each of the following:

| Secret Name | Value | Where to get it |
|---|---|---|
| `PRIVATE_KEY` | Your wallet private key (starts with `0x`) | MetaMask → Account Details → Export Private Key |
| `CLOB_API_KEY` | Your Polymarket API key | polymarket.com → Settings → API Keys |
| `CLOB_SECRET` | Your Polymarket secret | Same as above |
| `CLOB_PASSPHRASE` | Your Polymarket passphrase | Same as above |

To add each one:
- Click **New repository secret**
- Name: exactly as shown above (capitals matter)
- Value: paste your credential
- Click **Add secret**

---

## Step 5 — Set the DRY_RUN variable

Variables (non-sensitive settings) go in a different place than secrets.

1. Still in **Settings** → **Secrets and variables** → **Actions**
2. Click the **Variables** tab (next to Secrets)
3. Click **New repository variable**
4. Add this:

| Variable Name | Value |
|---|---|
| `DRY_RUN` | `true` |

This means the bot will scan and log but **not place real orders yet**.
Change it to `false` when you're ready to go live.

---

## Step 6 — Enable GitHub Actions

1. Click the **Actions** tab on your repository (top navigation)
2. You might see a prompt saying workflows are disabled — click **I understand my workflows, go ahead and enable them**
3. You should see **Polymarket Bot** listed on the left

---

## Step 7 — Run it manually to test

1. In the **Actions** tab, click **Polymarket Bot** on the left
2. Click **Run workflow** → **Run workflow** (green button)
3. Wait ~30 seconds, then refresh the page
4. Click the run that appeared → click **scan** → watch the live logs

You should see output like:
```
POLYMARKET BOT — SCAN STARTING
Mode:  🔵 DRY RUN
Fetched 312 active markets
Found 2 opportunities

🎯 OPPORTUNITY:
   Will X happen before end of month?
   Outcome:  Yes
   Price:    0.943 (94.3¢)
   ROI:      +6.04% if wins
   [DRY RUN] Would buy $5 USDC
```

If you see this — everything works! ✅

---

## Step 8 — Let it run automatically

From now on, **GitHub automatically runs the bot every 15 minutes, 24/7.**
You don't need to do anything. Your PC can be off.

To watch it run:
- Go to the **Actions** tab any time to see logs of every scan

---

## Step 9 — Go live when ready

Once you've watched a few days of dry run logs and you're happy with what it's finding:

1. Go to **Settings** → **Secrets and variables** → **Actions** → **Variables**
2. Click the pencil icon next to `DRY_RUN`
3. Change the value to `false`
4. Click **Update variable**

The next scheduled run (within 15 minutes) will place real orders. ✅

---

## How to check on the bot anytime

1. Go to **github.com/YOUR-USERNAME/polymarket-bot**
2. Click the **Actions** tab
3. You'll see a list of every run with timestamps
4. Click any run → click **scan** → see the full log

---

## How to pause the bot

1. Go to **Actions** tab
2. Click **Polymarket Bot** on the left
3. Click the **...** menu (top right of the workflow list)
4. Click **Disable workflow**

To restart: same steps → **Enable workflow**

---

## Troubleshooting

**The workflow isn't running automatically:**
GitHub sometimes delays scheduled workflows on inactive repos. Trigger it manually once
(Step 7) and it should start running on schedule after that.

**"Error: secrets not found":**
Double-check the secret names are exactly right (capitals, no spaces).

**Bot runs but finds 0 opportunities:**
This is normal! Not every scan will find something. The strategy only works when there
are markets about to close with prices in the 90–97¢ range. Check back after a few days.

**I want to change the trade size:**
Go to **Settings** → **Variables** → add `TRADE_SIZE_USDC` with your value (e.g. `7`).

---

## Summary

| Step | Action | Time |
|------|--------|------|
| 1 | Create GitHub account | 2 min |
| 2 | Create repository | 1 min |
| 3 | Upload bot files | 3 min |
| 4 | Add 4 secrets | 3 min |
| 5 | Set DRY_RUN variable | 1 min |
| 6 | Enable Actions | 1 min |
| 7 | Run manual test | 2 min |

**Total: ~13 minutes. Then it runs forever for free. 🚀**
