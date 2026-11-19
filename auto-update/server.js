/**
 * FluxMart — Auto-Update Server
 * Deploy on Render as a Web Service.
 */

require("dotenv").config();
const express = require("express");
const multer = require("multer");
const crypto = require("crypto");
const cookieParser = require("cookie-parser");
const fs = require("fs");
const path = require("path");

const app = express();
const PORT = process.env.PORT || 3000;
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || "changeme";

const UPLOADS_DIR = path.join(__dirname, "uploads");
const VERSION_FILE = path.join(__dirname, "data", "version.json");
const ZIP_PATH = path.join(UPLOADS_DIR, "update.zip");

// Ensure directories
fs.mkdirSync(UPLOADS_DIR, { recursive: true });
fs.mkdirSync(path.join(__dirname, "data"), { recursive: true });

// Init version.json if missing
if (!fs.existsSync(VERSION_FILE)) {
  fs.writeFileSync(VERSION_FILE, JSON.stringify({
    version: "3.3.4", sha256: "", size: "0 B", uploadedAt: ""
  }, null, 2));
}

app.use(cookieParser());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// ─── Public API ─────────────────────────────────────────────────────────────

app.get("/api/version", (req, res) => {
  try {
    const data = JSON.parse(fs.readFileSync(VERSION_FILE, "utf8"));
    res.json(data);
  } catch {
    res.status(500).json({ error: "Version info unavailable" });
  }
});

app.get("/api/download", (req, res) => {
  try {
    const data = JSON.parse(fs.readFileSync(VERSION_FILE, "utf8"));
    if (data.downloadUrl) {
      return res.redirect(data.downloadUrl);
    }
  } catch (e) {}

  if (!fs.existsSync(ZIP_PATH)) {
    return res.status(404).json({ error: "No update available" });
  }
  const stat = fs.statSync(ZIP_PATH);
  res.set({
    "Content-Type": "application/zip",
    "Content-Length": stat.size,
    "Content-Disposition": "attachment; filename=update.zip",
  });
  fs.createReadStream(ZIP_PATH).pipe(res);
});

// ─── Admin Auth ─────────────────────────────────────────────────────────────

const SESSION_TOKEN = crypto.randomBytes(32).toString("hex");

function isAuthed(req) {
  return req.cookies && req.cookies.msk_admin === SESSION_TOKEN;
}

app.post("/admin/login", (req, res) => {
  if (req.body.password === ADMIN_PASSWORD) {
    res.cookie("msk_admin", SESSION_TOKEN, { httpOnly: true, maxAge: 3600000 });
    return res.json({ success: true });
  }
  res.status(401).json({ success: false, error: "Wrong password" });
});

app.get("/admin/status", (req, res) => {
  if (!isAuthed(req)) return res.status(401).json({ error: "Not authenticated" });
  try {
    const data = JSON.parse(fs.readFileSync(VERSION_FILE, "utf8"));
    const hasZip = fs.existsSync(ZIP_PATH);
    res.json({ ...data, hasZip });
  } catch {
    res.json({ version: "unknown", hasZip: false });
  }
});

// ─── Admin Upload ───────────────────────────────────────────────────────────

const upload = multer({
  dest: path.join(UPLOADS_DIR, "tmp"),
  limits: { fileSize: 500 * 1024 * 1024 }, // 500 MB max
});

app.post("/admin/upload", upload.single("file"), (req, res) => {
  if (!isAuthed(req)) return res.status(401).json({ error: "Not authenticated" });
  if (!req.file) return res.status(400).json({ error: "No file uploaded" });

  const version = (req.body.version || "").trim();
  if (!version) {
    fs.unlinkSync(req.file.path);
    return res.status(400).json({ error: "Version is required" });
  }

  // Validate ZIP doesn't contain data/
  try {
    const AdmZip = require("adm-zip"); // optional, fallback if not available
    const zip = new AdmZip(req.file.path);
    const entries = zip.getEntries();
    for (const entry of entries) {
      const name = entry.entryName.replace(/\\/g, "/");
      if (name.startsWith("data/")) {
        fs.unlinkSync(req.file.path);
        return res.status(400).json({
          error: "ZIP contains data/ files. Remove them and re-upload."
        });
      }
    }
  } catch {
    // adm-zip not installed, skip validation (basic server)
  }

  // Calculate SHA256
  const hash = crypto.createHash("sha256");
  const stream = fs.createReadStream(req.file.path);
  stream.on("data", (chunk) => hash.update(chunk));
  stream.on("end", () => {
    stream.close(); // explicitly close to release the file descriptor
  });

  stream.on("close", () => {
    try {
      const sha256 = hash.digest("hex");
      const stat = fs.statSync(req.file.path);
      const sizeMB = (stat.size / 1024 / 1024).toFixed(1) + " MB";

      // Move file to final location
      if (fs.existsSync(ZIP_PATH)) {
        fs.unlinkSync(ZIP_PATH);
      }
      fs.renameSync(req.file.path, ZIP_PATH);

      // Update version.json
      const versionData = {
        version, sha256, size: sizeMB,
        uploadedAt: new Date().toISOString(),
      };
      fs.writeFileSync(VERSION_FILE, JSON.stringify(versionData, null, 2));

      res.json({ success: true, ...versionData });
    } catch (err) {
      console.error("Save error:", err);
      res.status(500).json({ error: "Failed to save update: " + err.message });
    }
  });

  stream.on("error", (err) => {
    res.status(500).json({ error: "Hash calculation failed: " + err.message });
  });
});

// ─── Admin Page ─────────────────────────────────────────────────────────────

app.get("/admin", (req, res) => {
  res.sendFile(path.join(__dirname, "public", "admin.html"));
});

// ─── Root ───────────────────────────────────────────────────────────────────

app.get("/", (req, res) => {
  res.json({ status: "FluxMart Update Server", online: true });
});

app.listen(PORT, () => {
  console.log(`MSK Update Server running on port ${PORT}`);
});
