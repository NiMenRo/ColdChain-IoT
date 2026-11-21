# Disposable PostgreSQL + authenticated MQTT/TLS integration.
# No existing container, volume, database or credential is modified.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$suffix = [guid]::NewGuid().ToString('N').Substring(0, 12)
$pg = "coldchain-b4-pg-$suffix"
$broker = "coldchain-b4-mqtt-$suffix"
$dbName = "b4_isolated_$suffix"
$tmp = Join-Path $env:TEMP 'opencode'
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$cfg = Join-Path $tmp "mosquitto-b4-$suffix.conf"
$report = Join-Path $tmp "qos-real-$suffix.json"
$certs = (Resolve-Path (Join-Path $root 'docker/mqtt/certs')).Path
@(
  'user root', 'listener 8883 0.0.0.0', 'allow_anonymous false',
  'password_file /tmp/passwd', 'cafile /certs/ca.crt',
  'certfile /certs/server.crt', 'keyfile /certs/server.key', 'persistence false'
) | Set-Content -Encoding ascii $cfg
$command = 'mosquitto_passwd -b -c /tmp/passwd b4test b4testonly && exec mosquitto -c /config/test.conf'
$pgId = $null
$mqttId = $null
Push-Location $root
try {
  $pgId = docker run -d --rm --name $pg -p '127.0.0.1::5432' -e POSTGRES_PASSWORD=b4testonly -e "POSTGRES_DB=$dbName" postgres:16-alpine
  if ($LASTEXITCODE -ne 0) { throw 'Could not start isolated PostgreSQL.' }
  $mqttId = docker run -d --rm --name $broker -p '127.0.0.1::8883' -v ("{0}:/certs:ro" -f $certs) -v ("{0}:/config/test.conf:ro" -f $cfg) --entrypoint sh eclipse-mosquitto:2 -c $command
  if ($LASTEXITCODE -ne 0) { throw 'Could not start isolated broker.' }
  $ready = $false
  for ($i = 0; $i -lt 30; $i++) {
    docker exec $pg pg_isready -U postgres -d $dbName 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 1
  }
  if (-not $ready) { throw 'Isolated PostgreSQL did not become ready.' }
  $pgPort = ((docker port $pg 5432/tcp) -split ':')[-1].Trim()
  $mqttPort = ((docker port $broker 8883/tcp) -split ':')[-1].Trim()
  if ($pgPort -notmatch '^\d+$' -or $mqttPort -notmatch '^\d+$') { throw 'Missing isolated port.' }
  $env:B4_DATABASE_URL = "postgresql+psycopg://postgres:b4testonly@127.0.0.1:$pgPort/$dbName"
  $env:DATABASE_URL = $env:B4_DATABASE_URL
  $env:B4_MQTT_PORT = $mqttPort
  $env:B4_MQTT_CA = Join-Path $certs 'ca.crt'
  $env:B4_MQTT_USER = 'b4test'
  $env:B4_MQTT_PASSWORD = 'b4testonly'
  $env:SMTP_ENABLED = 'false'
  $env:PUSH_ENABLED = 'false'
  $env:COLDCHAIN_SIM_WORKER_ENABLED = 'false'
  Push-Location backend
  try {
    .\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Isolated migration failed.' }
  } finally { Pop-Location }
  .\backend\.venv\Scripts\python.exe -B backend/scripts/validate_qos_dispatch_real.py |
    Set-Content -Encoding utf8 $report
  if ($LASTEXITCODE -ne 0) { throw 'Isolated integration failed.' }
  Write-Output "report=$report"
  $result = Get-Content -Raw $report | ConvertFrom-Json
  $result.cases | ForEach-Object {
    '{0}: mensajes={1}, lecturas={2}, clasificaciones={3}, QoS={4}, alertas={5}' -f $_.scenario, $_.messages, $_.readings, $_.classifications, $_.qos_rows, $_.alerts
  }
} finally {
  if ($mqttId) { docker stop $broker | Out-Null }
  if ($pgId) { docker stop $pg | Out-Null }
  Pop-Location
}
