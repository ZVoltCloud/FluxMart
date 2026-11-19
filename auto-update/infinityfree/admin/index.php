<?php
/**
 * FluxMart — Admin Panel (InfinityFree)
 * 1. Upload update.zip via InfinityFree File Manager to /uploads/
 * 2. Open this panel → click Search → enter version → Publish
 */

session_start();

// ─── Configuration ──────────────────────────────────────────────────────────
define('ADMIN_PASSWORD', 'msk');  // Change this!
// ─────────────────────────────────────────────────────────────────────────────

$dataDir     = __DIR__ . '/../data';
$uploadsDir  = __DIR__ . '/../uploads';
$versionFile = $dataDir . '/version.json';
$zipPath     = $uploadsDir . '/update.zip';

// Ensure directories exist
if (!is_dir($dataDir))    mkdir($dataDir, 0755, true);
if (!is_dir($uploadsDir)) mkdir($uploadsDir, 0755, true);

// Init version.json if missing
if (!file_exists($versionFile)) {
    file_put_contents($versionFile, json_encode([
        'version' => '3.3.0', 'sha256' => '', 'size' => '0 B', 'uploadedAt' => ''
    ], JSON_PRETTY_PRINT));
}

// ─── API Handlers ───────────────────────────────────────────────────────────
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $contentType = $_SERVER['CONTENT_TYPE'] ?? '';
    
    if (strpos($contentType, 'application/json') !== false) {
        $input = json_decode(file_get_contents('php://input'), true);
        $action = $input['action'] ?? '';
        header('Content-Type: application/json');
        
        // Login
        if ($action === 'login') {
            if (($input['password'] ?? '') === ADMIN_PASSWORD) {
                $_SESSION['msk_admin'] = true;
                echo json_encode(['success' => true]);
            } else {
                http_response_code(401);
                echo json_encode(['success' => false, 'error' => 'Wrong password']);
            }
            exit;
        }
        
        // Auth check for all other actions
        if (empty($_SESSION['msk_admin'])) {
            http_response_code(401);
            echo json_encode(['error' => 'Not authenticated']);
            exit;
        }
        
        // Search for update.zip
        if ($action === 'search') {
            if (file_exists($zipPath)) {
                $size = filesize($zipPath);
                $sizeMB = number_format($size / 1024 / 1024, 1) . ' MB';
                echo json_encode([
                    'found' => true,
                    'size' => $sizeMB,
                    'sizeBytes' => $size
                ]);
            } else {
                echo json_encode(['found' => false]);
            }
            exit;
        }
        
        // Publish — calculate SHA256 from existing ZIP and write version.json
        if ($action === 'publish') {
            $version = trim($input['version'] ?? '');
            if (empty($version)) {
                http_response_code(400);
                echo json_encode(['error' => 'Version is required']);
                exit;
            }
            if (!file_exists($zipPath)) {
                http_response_code(400);
                echo json_encode(['error' => 'No update.zip found. Upload it via File Manager first.']);
                exit;
            }
            
            // Calculate SHA256
            $sha256 = hash_file('sha256', $zipPath);
            $size   = filesize($zipPath);
            $sizeMB = number_format($size / 1024 / 1024, 1) . ' MB';
            
            $versionData = [
                'version'    => $version,
                'sha256'     => $sha256,
                'size'       => $sizeMB,
                'uploadedAt' => gmdate('Y-m-d\TH:i:s\Z'),
            ];
            
            file_put_contents($versionFile, json_encode($versionData, JSON_PRETTY_PRINT));
            
            echo json_encode(array_merge(['success' => true], $versionData));
            exit;
        }
        
        echo json_encode(['error' => 'Unknown action']);
        exit;
    }
}

// ─── API: Status (GET) ─────────────────────────────────────────────────────
if ($_SERVER['REQUEST_METHOD'] === 'GET' && isset($_GET['status'])) {
    header('Content-Type: application/json');
    
    if (empty($_SESSION['msk_admin'])) {
        http_response_code(401);
        echo json_encode(['error' => 'Not authenticated']);
        exit;
    }
    
    $data   = json_decode(file_get_contents($versionFile), true) ?: [];
    $hasZip = file_exists($zipPath);
    
    echo json_encode(array_merge($data, ['hasZip' => $hasZip]));
    exit;
}

// ─── Serve the admin HTML ──────────────────────────────────────────────────
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>FluxMart — Update Admin</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI',sans-serif;background:#000;color:#f0f0f0;min-height:100vh;display:flex;align-items:center;justify-content:center}
.container{width:100%;max-width:460px;padding:20px}
h1{font-size:20px;font-weight:600;color:#c0c0c0;margin-bottom:4px;text-align:center}
.subtitle{font-size:12px;color:#555;text-align:center;margin-bottom:28px}
.card{background:#0a0a0a;border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:24px;margin-bottom:16px}
.card h2{font-size:14px;color:#aaa;margin-bottom:16px;font-weight:500}
label{display:block;font-size:11px;color:#666;margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px}
input[type=text],input[type=password]{width:100%;padding:10px 12px;background:#111;border:1px solid rgba(255,255,255,.1);border-radius:8px;color:#f0f0f0;font-size:13px;font-family:inherit;outline:none;margin-bottom:14px;transition:border .2s}
input:focus{border-color:rgba(192,192,192,.4)}
.btn{padding:10px 24px;border:none;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;transition:all .2s;font-family:inherit;width:100%}
.btn-primary{background:#c0c0c0;color:#000}.btn-primary:hover{background:#d4d4d4}
.btn-search{background:#1a1a1a;color:#c0c0c0;border:1px solid rgba(255,255,255,.1)}.btn-search:hover{background:#222;border-color:rgba(192,192,192,.3)}
.btn:disabled{opacity:.4;cursor:not-allowed}
.status-box{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:14px;margin-bottom:16px}
.status-row{display:flex;justify-content:space-between;font-size:12px;margin-bottom:6px}
.status-row:last-child{margin-bottom:0}
.status-label{color:#666}
.status-value{color:#c0c0c0;font-weight:500}
.status-value.green{color:#4caf50}
.msg{font-size:12px;margin-top:10px;text-align:center;min-height:18px}
.msg.ok{color:#4caf50}
.msg.err{color:#f44336}
.msg.info{color:#c0c0c0}
#login-panel,#admin-panel{display:none}
#login-panel.active,#admin-panel.active{display:block}
.search-result{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:16px;margin-top:14px;display:none;text-align:center}
.search-result .found-icon{font-size:28px;margin-bottom:8px}
.search-result .found-text{font-size:13px;color:#c0c0c0;margin-bottom:4px}
.search-result .found-size{font-size:11px;color:#666}
.publish-form{display:none;margin-top:16px}
.separator{border:none;border-top:1px solid rgba(255,255,255,.06);margin:16px 0}
</style>
</head>
<body>
<div class="container">
  <h1>FluxMart</h1>
  <div class="subtitle">Update Server Admin Panel</div>

  <!-- Login -->
  <div id="login-panel" class="active">
    <div class="card">
      <h2>Admin Login</h2>
      <label>Password</label>
      <input type="password" id="login-pwd" placeholder="Enter admin password" autocomplete="off">
      <button class="btn btn-primary" id="login-btn" onclick="doLogin()">Login</button>
      <div class="msg" id="login-msg"></div>
    </div>
  </div>

  <!-- Admin -->
  <div id="admin-panel">
    <div class="card">
      <h2>Current Status</h2>
      <div class="status-box" id="status-box">
        <div class="status-row"><span class="status-label">Version</span><span class="status-value" id="s-ver">—</span></div>
        <div class="status-row"><span class="status-label">SHA256</span><span class="status-value" id="s-hash" style="font-size:10px;word-break:break-all">—</span></div>
        <div class="status-row"><span class="status-label">Size</span><span class="status-value" id="s-size">—</span></div>
        <div class="status-row"><span class="status-label">Uploaded</span><span class="status-value" id="s-date">—</span></div>
        <div class="status-row"><span class="status-label">ZIP Ready</span><span class="status-value" id="s-zip">—</span></div>
      </div>
    </div>

    <div class="card">
      <h2>Publish New Update</h2>
      <p style="font-size:11px;color:#555;margin-bottom:14px">
        Upload <b style="color:#888">update.zip</b> to <code style="color:#888">/uploads/</code> via File Manager, then click Search.
      </p>
      <button class="btn btn-search" id="search-btn" onclick="doSearch()">🔍 Search for update.zip</button>

      <!-- Search Result -->
      <div class="search-result" id="search-result">
        <div class="found-icon" id="search-icon">📦</div>
        <div class="found-text" id="search-text">—</div>
        <div class="found-size" id="search-size"></div>
      </div>

      <!-- Publish Form (shown after ZIP found) -->
      <div class="publish-form" id="publish-form">
        <hr class="separator">
        <label>Version Number</label>
        <input type="text" id="pub-ver" placeholder="e.g. 3.4.0">
        <button class="btn btn-primary" id="publish-btn" onclick="doPublish()">Publish Update</button>
      </div>

      <div class="msg" id="action-msg"></div>
    </div>
  </div>
</div>

<script>
function setMsg(id, text, type) {
  var el = document.getElementById(id);
  el.textContent = text;
  el.className = 'msg ' + (type || '');
}

async function apiPost(action, data) {
  var r = await fetch('', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(Object.assign({ action: action }, data || {}))
  });
  return await r.json();
}

// ─── Login ──────────────────────────────────────────────────────────────────

async function doLogin() {
  var pwd = document.getElementById('login-pwd').value;
  if (!pwd) { setMsg('login-msg', 'Enter password', 'err'); return; }
  document.getElementById('login-btn').disabled = true;
  try {
    var j = await apiPost('login', { password: pwd });
    if (j.success) {
      document.getElementById('login-panel').classList.remove('active');
      document.getElementById('admin-panel').classList.add('active');
      loadStatus();
    } else {
      setMsg('login-msg', j.error || 'Wrong password', 'err');
    }
  } catch (e) {
    setMsg('login-msg', 'Connection error', 'err');
  }
  document.getElementById('login-btn').disabled = false;
}

// ─── Status ─────────────────────────────────────────────────────────────────

async function loadStatus() {
  try {
    var r = await fetch('?status=1');
    if (r.status === 401) {
      document.getElementById('admin-panel').classList.remove('active');
      document.getElementById('login-panel').classList.add('active');
      return;
    }
    var j = await r.json();
    document.getElementById('s-ver').textContent = j.version || '—';
    document.getElementById('s-hash').textContent = j.sha256 ? j.sha256.substring(0,32) + '...' : '—';
    document.getElementById('s-size').textContent = j.size || '—';
    document.getElementById('s-date').textContent = j.uploadedAt ? new Date(j.uploadedAt).toLocaleString() : '—';
    var zipEl = document.getElementById('s-zip');
    zipEl.textContent = j.hasZip ? 'Yes' : 'No';
    zipEl.className = 'status-value ' + (j.hasZip ? 'green' : '');
  } catch {}
}

// ─── Search ─────────────────────────────────────────────────────────────────

async function doSearch() {
  var btn = document.getElementById('search-btn');
  btn.disabled = true;
  btn.textContent = 'Searching...';
  setMsg('action-msg', '', '');

  try {
    var j = await apiPost('search');
    var result = document.getElementById('search-result');
    var icon = document.getElementById('search-icon');
    var text = document.getElementById('search-text');
    var size = document.getElementById('search-size');
    var form = document.getElementById('publish-form');

    result.style.display = 'block';

    if (j.found) {
      icon.textContent = '✅';
      text.textContent = 'Found update.zip';
      size.textContent = j.size;
      form.style.display = 'block';
      document.getElementById('pub-ver').focus();
    } else {
      icon.textContent = '❌';
      text.textContent = 'No update.zip found';
      size.textContent = 'Upload it to /uploads/ via File Manager, then search again.';
      form.style.display = 'none';
    }
  } catch (e) {
    setMsg('action-msg', 'Connection error', 'err');
  }

  btn.disabled = false;
  btn.textContent = '🔍 Search for update.zip';
}

// ─── Publish ────────────────────────────────────────────────────────────────

async function doPublish() {
  var ver = document.getElementById('pub-ver').value.trim();
  if (!ver) { setMsg('action-msg', 'Enter a version number', 'err'); return; }

  var btn = document.getElementById('publish-btn');
  btn.disabled = true;
  btn.textContent = 'Publishing...';
  setMsg('action-msg', 'Calculating SHA256 hash...', 'info');

  try {
    var j = await apiPost('publish', { version: ver });
    if (j.success) {
      setMsg('action-msg', '✓ Published v' + j.version + ' — SHA256: ' + j.sha256.substring(0,16) + '...', 'ok');
      document.getElementById('pub-ver').value = '';
      loadStatus();
    } else {
      setMsg('action-msg', j.error || 'Publish failed', 'err');
    }
  } catch (e) {
    setMsg('action-msg', 'Connection error', 'err');
  }

  btn.disabled = false;
  btn.textContent = 'Publish Update';
}

document.getElementById('login-pwd').addEventListener('keypress', function(e) {
  if (e.key === 'Enter') doLogin();
});
document.getElementById('pub-ver') && document.getElementById('pub-ver').addEventListener('keypress', function(e) {
  if (e.key === 'Enter') doPublish();
});
</script>
</body>
</html>
