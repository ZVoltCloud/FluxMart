<?php
/**
 * FluxMart — GET /api/download
 * Serves update.zip to the Bootstrapper client.
 * 
 * Priority:
 *   1. If version.json has a "downloadUrl" field → redirect there (Dropbox, etc.)
 *   2. Otherwise serve uploads/update.zip directly
 */

header('Access-Control-Allow-Origin: *');

$versionFile = __DIR__ . '/../data/version.json';
$zipPath     = __DIR__ . '/../uploads/update.zip';

// 1. Check for external download URL in version.json
if (file_exists($versionFile)) {
    $data = json_decode(file_get_contents($versionFile), true);
    if (!empty($data['downloadUrl'])) {
        header('Location: ' . $data['downloadUrl']);
        exit;
    }
}

// 2. Serve local ZIP file
if (!file_exists($zipPath)) {
    http_response_code(404);
    header('Content-Type: application/json');
    echo json_encode(['error' => 'No update available']);
    exit;
}

$fileSize = filesize($zipPath);

header('Content-Type: application/zip');
header('Content-Length: ' . $fileSize);
header('Content-Disposition: attachment; filename="update.zip"');
header('Cache-Control: no-cache');

// Stream the file in chunks to avoid memory issues with large files
$fp = fopen($zipPath, 'rb');
if ($fp === false) {
    http_response_code(500);
    header('Content-Type: application/json');
    echo json_encode(['error' => 'Failed to read update file']);
    exit;
}

while (!feof($fp)) {
    echo fread($fp, 8192);
    ob_flush();
    flush();
}

fclose($fp);
