<?php
/**
 * FluxMart — Auto-Update Server (InfinityFree)
 * Root endpoint — status check
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');

echo json_encode([
    'status' => 'FluxMart Update Server',
    'online' => true,
    'host'   => 'InfinityFree'
]);
