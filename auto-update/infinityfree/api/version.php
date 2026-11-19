<?php
/**
 * FluxMart — GET /api/version
 * Returns version info from data/version.json
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Cache-Control: no-cache, no-store, must-revalidate');

$versionFile = __DIR__ . '/../data/version.json';

if (!file_exists($versionFile)) {
    http_response_code(500);
    echo json_encode(['error' => 'Version info unavailable']);
    exit;
}

$data = file_get_contents($versionFile);
if ($data === false) {
    http_response_code(500);
    echo json_encode(['error' => 'Failed to read version info']);
    exit;
}

// Validate it's proper JSON
$decoded = json_decode($data, true);
if ($decoded === null) {
    http_response_code(500);
    echo json_encode(['error' => 'Invalid version data']);
    exit;
}

echo json_encode($decoded);
