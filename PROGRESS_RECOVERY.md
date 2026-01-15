# Progress Recovery Guide

## Why Progress Can Be Lost

Streamlit Cloud uses an **ephemeral filesystem** - files stored locally can be wiped when:
- App goes to sleep (free tier after ~7 days inactivity)
- App is redeployed (code changes pushed)
- Container restarts
- Server maintenance

**Important:** Your evaluation **DATA** is always safe in Google Sheets! Only the progress indicators (which queries show as "started" or "completed") can be lost.

## Prevention Strategies

### ✅ **AUTOMATIC Recovery (Recommended)**
The app now automatically recovers progress from Google Sheets on startup!

**Setup (one-time):**
1. Add the `doGet()` function to your Google Apps Script (see `google_apps_script_get_endpoint.txt`)
2. Deploy it as a web app with "Execute as: Me" and "Who has access: Anyone"
3. That's it! Progress will auto-recover on every app restart

**How it works:**
- On startup, if `evaluations.json` is empty, the app calls Google Sheets
- Retrieves all submitted evaluations
- Automatically rebuilds progress tracking
- **No manual intervention needed!**

### ✅ Manual Recovery (Backup Method)
If automatic recovery isn't set up yet:
1. Export Google Sheet as CSV (File → Download → CSV)
2. Go to Admin Dashboard → "🔧 Recover Progress from Google Sheets"
3. Upload the CSV
4. Progress is instantly restored

## Recovery Steps

1. **Export Google Sheet:**
   - Open your Google Sheet with submitted evaluations
   - File → Download → Comma-separated values (.csv)

2. **Recover via Admin Dashboard:**
   - Login as Admin (password: `GMK-admin-dashboard-2024`)
   - Expand "🔧 Recover Progress from Google Sheets"
   - Upload the CSV file
   - Progress is restored instantly

3. **Or use recovery script locally:**
   ```bash
   cd /Users/stefanoleitner/CursorProjects/gmk
   python recover_progress.py
   ```

## About Reboot Times

Streamlit Cloud deployments typically take:
- **5-15 minutes** on free tier
- White screen with loading icon is **normal** during deployment
- You'll see logs like "Python dependencies were installed" - this is expected
- Be patient - the app will come back online!

## Data Safety

✅ **All evaluation data is permanently stored in Google Sheets**
✅ **Progress can always be recovered from Google Sheets**
✅ **No evaluation work is ever lost**

The progress indicators are just for convenience - they help evaluators see what they've completed. If they're lost, they can be rebuilt from Google Sheets data.

