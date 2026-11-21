[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8765
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$settings = Join-Path $root '.env.local'
$project = if ($env:COMPOSE_PROJECT_NAME) { $env:COMPOSE_PROJECT_NAME } else { 'marsad-local' }

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Install Docker Desktop and start it, then run this script again.'
}
docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Docker Compose is required.' }
docker info --format '{{.OSType}}' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop and wait for the engine to be ready.' }

if (-not (Test-Path -LiteralPath $settings)) {
    $configuration = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'platform.env.example'))
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        foreach ($name in 'MARSAD_DB_PASSWORD', 'MARSAD_DISPATCH_PASSWORD', 'MARSAD_MIGRATION_PASSWORD') {
            $buffer = New-Object byte[] 32
            $random.GetBytes($buffer)
            $password = [BitConverter]::ToString($buffer).Replace('-', '').ToLowerInvariant()
            $configuration = [regex]::Replace($configuration, "(?m)^${name}=(?=\r?$)", "$name=$password")
        }
    } finally {
        $random.Dispose()
    }
    $configuration = $configuration.Replace('MARSAD_PORT=8765', "MARSAD_PORT=$Port")
    $configuration = $configuration.Replace('http://127.0.0.1:8765/', "http://127.0.0.1:$Port/")
    $file = [IO.File]::Open($settings, [IO.FileMode]::CreateNew)
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($configuration)
        $file.Write($bytes, 0, $bytes.Length)
    } finally {
        $file.Dispose()
    }
}

Push-Location -LiteralPath $root
try {
    $compose = @('-p', $project, '-f', 'compose.yaml', '-f', 'compose.local.yaml', '--env-file', '.env.local')
    docker compose @compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'Marsad failed to start. Check the Docker Compose output above.' }
    $published = docker compose @compose port app 8000
    if ($LASTEXITCODE -ne 0 -or -not $published) { throw 'Marsad did not publish its local web port.' }
    $url = "http://$published"
    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    $options = $null
    while (-not $options -and [DateTime]::UtcNow -lt $deadline) {
        try {
            $options = Invoke-RestMethod "$url/api/platform/auth/options" -TimeoutSec 3
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $options) { throw 'Marsad did not become ready. Check the app logs in Docker Desktop.' }
    if (-not ($options.password -and $options.registration)) {
        throw 'Marsad responded, but local sign-in or registration is disabled.'
    }
    Write-Host "Open $url/signin to sign in or create an account."
} finally {
    Pop-Location
}
