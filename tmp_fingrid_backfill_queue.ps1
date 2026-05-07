$ids = 281,283,315,316,318
foreach ($id in $ids) {
  $started = $false
  while (-not $started) {
    try {
      Invoke-WebRequest -UseBasicParsing -Method Post "http://127.0.0.1:8085/api/fingrid/datasets/$id/sync?mode=backfill" | Out-Null
      $started = $true
    } catch {
      Start-Sleep -Seconds 15
    }
  }

  $done = $false
  while (-not $done) {
    try {
      $payload = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8085/api/fingrid/datasets/$id/status").Content | ConvertFrom-Json
      if ($payload.status.sync_status -eq 'ok' -and $payload.status.backfill_completed_at) {
        $done = $true
      } elseif ($payload.status.sync_status -eq 'error') {
        $done = $true
      } else {
        Start-Sleep -Seconds 30
      }
    } catch {
      Start-Sleep -Seconds 30
    }
  }
}
