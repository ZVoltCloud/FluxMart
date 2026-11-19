# FluxMart — InfinityFree Auto-Update Server

## Directory Structure

Upload the **contents** of this `infinityfree/` folder to your InfinityFree site's `htdocs/` directory.

```
htdocs/
├── .htaccess            # URL routing (api/version → api/version.php)
├── index.php            # Root status endpoint
├── api/
│   ├── version.php      # GET /api/version — returns version.json
│   └── download.php     # GET /api/download — serves update.zip
├── admin/
│   └── index.php        # Admin panel (password protected)
├── data/
│   └── version.json     # Version metadata
└── uploads/
    ├── .htaccess         # Blocks direct access to ZIPs
    └── update.zip        # The update file (uploaded by you)
```

## Setup Steps

1. **Create InfinityFree account** at https://www.infinityfree.com/
2. **Create a new site** (you'll get a subdomain like `yoursite.infinityfreeapp.com`)
3. **Open File Manager** and navigate to `htdocs/`
4. **Upload all files** from this `infinityfree/` folder into `htdocs/`
5. **Change the admin password** in `admin/index.php` (line: `define('ADMIN_PASSWORD', 'msk');`)
6. **Update Bootstrapper.py** — set `_UPDATE_URL` to your InfinityFree URL

## Publishing Updates

### Option A: Admin Panel (easiest)
1. Upload `update.zip` to `/uploads/` via File Manager
2. Go to `https://yoursite.infinityfreeapp.com/admin`
3. Login and enter the new version number
4. Click "Publish" — SHA256 is auto-calculated

### Option B: Local Script
1. Run `python publish_update.py`
2. Upload the generated `update.zip` and `version.json` via File Manager

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Server status (JSON) |
| `/api/version` | GET | Returns version info |
| `/api/download` | GET | Downloads update.zip |
| `/admin` | GET | Admin panel |
