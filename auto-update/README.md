# FluxMart — Auto-Update Server

## Deploy on Render

1. Push this `auto-update/` folder to a Git repo (GitHub/GitLab)
2. Go to [render.com](https://render.com) → New → **Web Service**
3. Connect your repo
4. Settings:
   - **Root Directory**: `auto-update`
   - **Build Command**: `npm install`
   - **Start Command**: `node server.js`
5. Environment Variables:
   - `ADMIN_PASSWORD` = your secret password
6. Deploy!

## Usage

### Admin Panel
Go to `https://your-app.onrender.com/admin`
- Enter your password
- Type the new version number (e.g. `3.3.2`)
- Upload your `update.zip`
- SHA256 hash is calculated automatically

### API Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/version` | GET | Returns current version + SHA256 |
| `/api/download` | GET | Downloads update.zip |
| `/admin` | GET | Admin panel |

### Creating update.zip
From your `dist/` folder after running `exe.py`:
1. Select everything EXCEPT `data/` folder
2. Zip it
3. Upload via admin panel

**Never include `data/` in the ZIP!**

## Files
```
auto-update/
├── server.js          ← Express server
├── package.json       ← Dependencies
├── .env.example       ← Env template
├── data/
│   └── version.json   ← Current version info
├── uploads/
│   └── update.zip     ← The update file
└── public/
    └── admin.html     ← Admin panel UI
```
