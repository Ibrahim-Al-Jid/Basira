[CmdletBinding()]
param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8765,
    # Optional. Public identifiers of the GitHub App, written to .env.local only when those lines are empty.
    [string]$GitHubClientId = '',
    [string]$GitHubAppSlug = '',
    # Start the model gateway and write its settings to .env.local (also on when BASIRA_PROJECT_MODEL_ENABLED=1 is already there).
    [switch]$Model
)

$ErrorActionPreference = 'Stop'

function Get-Setting([string]$text, [string]$name) {
    $m = [regex]::Match($text, "(?m)^${name}=(.*?)\r?$")
    if ($m.Success) { return $m.Groups[1].Value.Trim() }
    return ''
}

function Set-Setting([string]$text, [string]$name, [string]$value) {
    $pattern = "(?m)^${name}=.*?(?=\r?$)"
    if ([regex]::IsMatch($text, $pattern)) {
        return [regex]::Replace($text, $pattern, { param($m) "${name}=$value" })
    }
    return $text.TrimEnd("`r", "`n") + "`n${name}=$value`n"
}

function Test-CredentialKey([string]$key) {
    # A Fernet key is 32 random bytes in URL-safe base64.
    if ($key -notmatch '^[A-Za-z0-9_-]{43}=$') { return $false }
    try {
        return ([Convert]::FromBase64String($key.Replace('-', '+').Replace('_', '/'))).Length -eq 32
    } catch { return $false }
}

function New-RandomText([int]$bytes) {
    $buffer = New-Object byte[] $bytes
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $random.GetBytes($buffer) } finally { $random.Dispose() }
    return [BitConverter]::ToString($buffer).Replace('-', '').ToLowerInvariant()
}

# Returns $true when the model gateway profile must be started.
function Initialize-ModelSettings([string]$path, [bool]$requested) {
    $text = [IO.File]::ReadAllText($path)
    $enabled = (Get-Setting $text 'BASIRA_PROJECT_MODEL_ENABLED') -eq '1'
    if (-not ($requested -or $enabled)) { return $false }
    $original = $text
    $text = Set-Setting $text 'BASIRA_PROJECT_MODEL_ENABLED' '1'
    if (-not (Get-Setting $text 'BASIRA_GATEWAY_URL')) {
        $text = Set-Setting $text 'BASIRA_GATEWAY_URL' 'http://model-gateway:8001'
    }
    if (-not (Get-Setting $text 'BASIRA_GATEWAY_TOKEN')) {
        $text = Set-Setting $text 'BASIRA_GATEWAY_TOKEN' (New-RandomText 32)
    }
    $dbPassword = Get-Setting $text 'BASIRA_MODEL_DB_PASSWORD'
    if (-not $dbPassword) {
        $text = Set-Setting $text 'BASIRA_MODEL_DB_PASSWORD' (New-RandomText 24)
    } elseif ($dbPassword -notmatch '^[0-9A-Za-z]{24,128}$') {
        throw 'BASIRA_MODEL_DB_PASSWORD in .env.local must be 24 to 128 letters or digits. Clear the value and run this script again to get a new one.'
    }
    if ($text -ne $original) {
        [IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding($false)))
    }
    return $true
}

function Initialize-GitHubSettings([string]$path, [int]$port, [string]$clientId, [string]$slug) {
    $text = [IO.File]::ReadAllText($path)
    $original = $text
    $listening = Get-Setting $text 'BASIRA_PORT'
    if ($listening -match '^\d+$') { $port = [int]$listening }
    if (-not (Get-Setting $text 'BASIRA_GITHUB_CALLBACK_URL')) {
        $text = Set-Setting $text 'BASIRA_GITHUB_CALLBACK_URL' "http://127.0.0.1:$port/api/platform/github/callback"
    }
    if ($clientId -and -not (Get-Setting $text 'BASIRA_GITHUB_CLIENT_ID')) {
        $text = Set-Setting $text 'BASIRA_GITHUB_CLIENT_ID' $clientId
    }
    if ($slug -and -not (Get-Setting $text 'BASIRA_GITHUB_APP_SLUG')) {
        $text = Set-Setting $text 'BASIRA_GITHUB_APP_SLUG' $slug
    }
    if (-not (Get-Setting $text 'BASIRA_GITHUB_CREDENTIAL_KEY')) {
        $buffer = New-Object byte[] 32
        $random = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $random.GetBytes($buffer) } finally { $random.Dispose() }
        $key = [Convert]::ToBase64String($buffer).Replace('+', '-').Replace('/', '_')
        $text = Set-Setting $text 'BASIRA_GITHUB_CREDENTIAL_KEY' $key
    }
    if ((Get-Setting $text 'BASIRA_GITHUB_CLIENT_ID') -and -not (Get-Setting $text 'BASIRA_GITHUB_CLIENT_SECRET') `
            -and [Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
        $secure = Read-Host 'Paste the GitHub App Client Secret (hidden, saved only in .env.local)' -AsSecureString
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $secret = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
        if ($secret) { $text = Set-Setting $text 'BASIRA_GITHUB_CLIENT_SECRET' $secret.Trim() }
    }
    if ($text -ne $original) {
        [IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding($false)))
    }
    if (-not (Test-CredentialKey (Get-Setting $text 'BASIRA_GITHUB_CREDENTIAL_KEY'))) {
        throw 'BASIRA_GITHUB_CREDENTIAL_KEY in .env.local is not a valid key (32 random bytes in URL-safe base64, 44 characters ending with =). Clear the value and run this script again to get a new one. Connections saved with the old key must be reconnected.'
    }
    $missing = @('BASIRA_GITHUB_CLIENT_ID', 'BASIRA_GITHUB_CLIENT_SECRET', 'BASIRA_GITHUB_APP_SLUG') |
        Where-Object { -not (Get-Setting $text $_) }
    if ($missing) {
        Write-Warning ("GitHub connection is not configured yet. Empty in .env.local: " + ($missing -join ', ') +
            ". Fill them and run this script again; the app starts without GitHub until then.")
    }
}
$root = Split-Path -Parent $PSScriptRoot
$settings = Join-Path $root '.env.local'
$project = if ($env:COMPOSE_PROJECT_NAME) { $env:COMPOSE_PROJECT_NAME } else { 'basira-local' }

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
        foreach ($name in 'BASIRA_DB_PASSWORD', 'BASIRA_DISPATCH_PASSWORD', 'BASIRA_MIGRATION_PASSWORD') {
            $buffer = New-Object byte[] 32
            $random.GetBytes($buffer)
            $password = [BitConverter]::ToString($buffer).Replace('-', '').ToLowerInvariant()
            $configuration = [regex]::Replace($configuration, "(?m)^${name}=(?=\r?$)", "$name=$password")
        }
    } finally {
        $random.Dispose()
    }
    $configuration = $configuration.Replace('BASIRA_PORT=8765', "BASIRA_PORT=$Port")
    $configuration = $configuration.Replace('http://127.0.0.1:8765/', "http://127.0.0.1:$Port/")
    $file = [IO.File]::Open($settings, [IO.FileMode]::CreateNew)
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($configuration)
        $file.Write($bytes, 0, $bytes.Length)
    } finally {
        $file.Dispose()
    }
}

Initialize-GitHubSettings $settings $Port $GitHubClientId $GitHubAppSlug
$withModel = Initialize-ModelSettings $settings ([bool]$Model)

Push-Location -LiteralPath $root
try {
    $compose = @('-p', $project, '-f', 'compose.yaml', '-f', 'compose.local.yaml', '--env-file', '.env.local')
    if ($withModel) { $compose += @('--profile', 'model') }
    docker compose @compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw 'Basira failed to start. Check the Docker Compose output above.' }
    $published = docker compose @compose port app 8000
    if ($LASTEXITCODE -ne 0 -or -not $published) { throw 'Basira did not publish its local web port.' }
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
    if (-not $options) { throw 'Basira did not become ready. Check the app logs in Docker Desktop.' }
    if (-not ($options.password -and $options.registration)) {
        throw 'Basira responded, but local sign-in or registration is disabled.'
    }
    Write-Host "Open $url/signin to sign in or create an account."
} finally {
    Pop-Location
}
