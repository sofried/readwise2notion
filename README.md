# Readwise to Notion Sync

Automatically sync your Readwise highlights to a Notion database. This script runs on GitHub Actions, so it syncs automatically in the cloud without needing your computer to be on!

## ✨ Features

- 🔄 **Automatic syncing** - Runs every hour from 5 AM to 5 PM CST
- ⚡ **Smart & efficient** - Only processes books with new highlights since last sync
- 📚 **Complete metadata** - Syncs title, author, category, highlights, cover images, and more
- 🎨 **Beautiful formatting** - Highlights appear as clean quote blocks in Notion
- 🚫 **No duplicates** - Smart detection prevents duplicate highlights
- ☁️ **Cloud-based** - Runs on GitHub Actions (free!)

## 📋 What Gets Synced

For each item in Readwise (books, articles, podcasts, tweets, PDFs, etc.):
- ✅ Title, Author, Category
- ✅ Cover image (as page icon and cover)
- ✅ Highlight count
- ✅ All highlight text (as quote blocks in chronological order)
- ✅ Your notes on highlights
- ✅ Last highlighted date
- ✅ Last synced timestamp
- ✅ Link to view in Readwise

**Notes:** 
- **Manual edits are protected:** Once synced, only NEW highlights (created after last sync) are added. If you delete or edit highlights in Notion, they won't come back!

## Great [FREE template](https://www.notion.so/templates/ultimate-reading-tracker-948) that works perfectly with this sync!

## 🚀 Quick Setup (10 minutes) 7 min Video Guide [Here](https://youtu.be/LM30oxEo_3I)

### Step 1: Get Your API Tokens

#### Readwise Token
1. Go to https://readwise.io/access_token
2. Copy your token (it looks like: `gVoJIF...`)

#### Notion Token
1. Go to https://www.notion.so/my-integrations
2. Click **"+ New integration"**
3. Give it a name: "Readwise Sync"
4. Click **"Submit"**
5. Copy the **Internal Integration Token** (starts with `secret_` or `ntn_`)

### Step 2: Connect Integration to Your Notion Database

1. Open your Notion workspace
2. Go to the database where you want highlights synced
3. Click the **"•••"** menu in the top-right
4. Click **"Add connections"**
5. Select your **"Readwise Sync"** integration
6. Click **"Confirm"**

### Step 3: Get Your Notion Database ID

Your database URL looks like:
```
https://www.notion.so/workspace/1762bb83799381ad8869c0b790c557af?v=...
                                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                 This is your Database ID
```

The Database ID is the 32-character string (with or without dashes).

### Step 4: Set Up This Repository

1. **Fork or clone this repository**
   - Click the "Fork" button at the top of this page, OR
   - Click "Use this template" to create your own copy

2. **Add your secrets** (these are kept private!)
   - Go to your repository
   - Click **Settings** → **Secrets and variables** → **Actions**
   - Click **"New repository secret"**
   - Add these secrets:

   **Required Secrets:**
   | Name | Value | Example |
   |------|-------|---------|
   | `READWISE_TOKEN` | Your Readwise access token | `gVoJIFpTJS8...` |
   | `NOTION_TOKEN` | Your Notion integration token | `ntn_117358903...` or `secret_...` |
   | `NOTION_DATABASE_ID` | Your database ID (with or without dashes) | `1762bb83799381ad8869c0b790c557af` |

   **Optional Secrets:**
   | Name | Value | Description |
   |------|-------|-------------|
   | `DAYS_TO_SYNC` | Number (e.g., `7`, `14`, `30`) | Limit sync to highlights from last N days. If not set, syncs all new highlights since last run. |

### Step 5: Configure Your Notion Database

Your Notion database needs these properties (columns):

**Required Properties:**
- `Title` (Title type)
- `Category` (Select type) with options: `Books`, `Articles`, `Quote`, `Podcast`
- `Status` (Status type) with option: `Not started`
- `Highlights` (Number type)

**Optional but Recommended:**
- `Author` (Text type)
- `Last Synced` (Date type)
- `Last Highlighted` (Date type)
- `URL` (URL type)

> **Note:** The script will still work if optional properties are missing - it will just skip them.

### Step 6: Enable GitHub Actions

1. Go to the **Actions** tab in your repository
2. Click **"I understand my workflows, go ahead and enable them"**
3. The sync will run automatically every hour from 5 AM to 5 PM CST!

### Step 7: Test It! (Optional)

Want to test before waiting for the schedule?

1. Go to **Actions** tab
2. Click **"Readwise to Notion Sync"** workflow
3. Click **"Run workflow"** → **"Run workflow"**
4. Watch it run!
5. Check your Notion database for synced highlights 🎉

---

## ⚡ How It Works (Efficiency)

The script uses multiple optimizations to be as fast as possible:

### **Optimization 1: Time-Based Filtering**
**First Run:**
- Syncs ALL your Readwise items to Notion (books, articles, podcasts, tweets, etc.)

**Subsequent Runs:**
- Only checks items that have NEW highlights since the last sync
- Skips everything else (much faster!)
- Uses Readwise's `updatedAfter` filter to be efficient

### **Optimization 2: Skip Unchanged Highlights**
If an item already exists in Notion and the highlight count hasn't changed, the script skips fetching and checking highlights entirely.

**Example:**
- You re-read an old article but don't add new highlights
- The script updates metadata but skips the highlight sync
- Saves API calls and processing time

### **The Result:**
The script saves a timestamp file (`.last_sync_time.json`) to track the last successful sync. This means:
- ✅ Fast syncs (only processes what changed)
- ✅ Minimal API usage (batch queries + smart skipping)
- ✅ No wasted time checking items without new highlights
- ✅ Respects deletions (won't recreate items you've deleted from Notion)

**Real-World Example:**
- You have 500 items in Readwise (books, articles, podcasts, etc.)
- You highlight from 2 articles today
- 1 Notion query + only fetch highlights for changed items ✅

---

## ⚙️ Customization

### Change Sync Schedule

The default schedule runs **every hour from 5 AM to 5 PM CST**.

To change this, edit `.github/workflows/sync.yml`:

```yaml
schedule:
  - cron: '0 11-23 * * *'  # Every hour from 5 AM to 5 PM CST
```

**Common schedules:**

```yaml
# Every hour, 24/7
- cron: '0 * * * *'

# Every 6 hours
- cron: '0 */6 * * *'

# Once daily at 2 AM CST (8 AM UTC)
- cron: '0 8 * * *'

# Twice daily (8 AM and 8 PM CST)
- cron: '0 14,2 * * *'
```

> **Tip:** Use [crontab.guru](https://crontab.guru/) to create custom schedules!

### Change Category Mapping

Different Readwise categories map to your Notion categories.

Edit `readwise_notion_sync.py`, line ~31:

```python
CATEGORY_MAP = {
    "books": "Books",
    "articles": "Articles",
    "tweets": "Quote",
    "podcasts": "Podcast",
    "supplementals": "Articles"
}
```

Change the values on the right to match your Notion category options.
```

**Option 2: Use command line (one-time override)**

```bash
# Sync only last 7 days
python readwise_notion_sync.py --days 7

# Sync only last 30 days
python readwise_notion_sync.py --days 30

# Sync everything (ignore last sync time)
python readwise_notion_sync.py --all
```

---

## 🐛 Troubleshooting

### "Secrets not found" error
- Make sure you added all three secrets: `READWISE_TOKEN`, `NOTION_TOKEN`, `NOTION_DATABASE_ID`
- Secret names are case-sensitive!

### "Property does not exist" error
- Check that your Notion database has all required properties
- Make sure property names match exactly (case-sensitive)

### No highlights appearing
- Make sure you gave the integration access to your database (Step 2)
- Check that your database ID is correct
- Verify highlights exist in Readwise

### Wrong category values
- Update the `CATEGORY_MAP` in `readwise_notion_sync.py` to match your Notion categories

### Sync isn't running automatically
- Check the Actions tab for errors
- Make sure GitHub Actions are enabled
- Verify the workflow file is in `.github/workflows/sync.yml`

---

## 📊 Monitoring

### Check Sync Status
1. Go to **Actions** tab
2. See recent runs and their status
3. Click any run to see detailed logs

### View Logs
Click on any workflow run to see:
- How many items were synced
- Which items were new vs. updated
- Any errors that occurred

---

## 🔒 Privacy & Security

- Your API tokens are stored as **GitHub Secrets** (encrypted and never exposed)
- The script only syncs data from Readwise to Notion
- No data is stored anywhere else
- You can revoke access anytime by deleting the Notion integration

---

## 📝 License

MIT License - Feel free to use and modify!

---

## 🙋 Questions?

- **Readwise API Docs:** https://readwise.io/api_deets
- **Notion API Docs:** https://developers.notion.com/
- **GitHub Actions Docs:** https://docs.github.com/en/actions

---

## 🎉 Credits
Created to make syncing Readwise highlights to Notion seamless and automatic!

If you find this useful, give it a ⭐️ on GitHub! 
[Buy me a coffee](https://buymeacoffee.com/leorule)

Created to make syncing Readwise highlights to Notion seamless and automatic!

If you find this useful, give it a ⭐️ on GitHub!
