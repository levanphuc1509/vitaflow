$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = Join-Path $projectRoot "venv\Scripts\python.exe"
}
if (-not (Test-Path $python)) {
    throw "Khong tim thay Python trong .venv hoac venv."
}

$wifiConfig = Get-NetIPConfiguration | Where-Object {
    $_.NetAdapter.Status -eq "Up" -and
    ($_.InterfaceAlias -match "Wi-?Fi|Wireless|WLAN" -or $_.NetAdapter.InterfaceDescription -match "Wi-?Fi|Wireless|WLAN") -and
    @($_.IPv4Address | Where-Object { $_.IPAddress -notmatch "^(127\.|169\.254\.)" }).Count -gt 0
} | Select-Object -First 1

if (-not $wifiConfig) {
    $wifiConfig = Get-NetIPConfiguration | Where-Object {
        $_.NetAdapter.Status -eq "Up" -and $_.IPv4DefaultGateway -and
        @($_.IPv4Address | Where-Object { $_.IPAddress -notmatch "^(127\.|169\.254\.)" }).Count -gt 0
    } | Select-Object -First 1
}
if (-not $wifiConfig) {
    throw "Khong tim thay dia chi IPv4 cua Wi-Fi. Hay ket noi Wi-Fi roi thu lai."
}

$ipAddress = $wifiConfig.IPv4Address |
    Where-Object { $_.IPAddress -notmatch "^(127\.|169\.254\.)" } |
    Select-Object -First 1
if (-not $ipAddress) {
    throw "Wi-Fi khong co dia chi IPv4 hop le."
}

$ip = $ipAddress.IPAddress
$url = "http://${ip}:5000"
$localUrl = "http://127.0.0.1:5000/"
$capacitorConfigPath = Join-Path $projectRoot "mobile-app\capacitor.config.json"
$json = Get-Content -Raw -Path $capacitorConfigPath
$urlPattern = [System.Text.RegularExpressions.Regex]::new('"url"\s*:\s*"[^"]*"')
$navigationPattern = [System.Text.RegularExpressions.Regex]::new('"allowNavigation"\s*:\s*\[[^\]]*\]')
if (-not $urlPattern.IsMatch($json) -or -not $navigationPattern.IsMatch($json)) {
    throw "Khong tim thay server.url hoac server.allowNavigation trong capacitor.config.json."
}
$json = $urlPattern.Replace($json, ('"url": "' + $url + '"'), 1)
$json = $navigationPattern.Replace($json, ('"allowNavigation": ["' + $ip + '"]'), 1)
$null = $json | ConvertFrom-Json
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($capacitorConfigPath, $json + [Environment]::NewLine, $utf8NoBom)

$listener = Get-NetTCPConnection -State Listen -LocalPort 5000 -ErrorAction SilentlyContinue
if ($listener) {
    throw "Cong 5000 dang duoc su dung. Hay dung server cu truoc khi chay lai."
}

$env:FLASK_HOST = "0.0.0.0"
$env:FLASK_DEBUG = "0"
$env:PORT = "5000"
$server = Start-Process -FilePath $python -ArgumentList "app.py" -WorkingDirectory $projectRoot -PassThru -NoNewWindow

try {
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($server.HasExited) {
            throw "Flask da dung som. Kiem tra loi hien thi trong terminal."
        }
        try {
            Invoke-WebRequest -Uri "http://127.0.0.1:5000/" -TimeoutSec 2 -UseBasicParsing | Out-Null
            $ready = $true
            break
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    if (-not $ready) {
        throw "Server khong phan hoi tai http://127.0.0.1:5000 sau 30 giay."
    }

    Write-Host ""
    Write-Host "VitaFlow server da san sang."
    Write-Host "Mang duoc chon: $($wifiConfig.InterfaceAlias)"
    Write-Host "May tinh: $localUrl"
    Write-Host "Dien thoai cung Wi-Fi: $url"
    Write-Host "Dang mo trang tren may tinh..."
    Write-Host "Neu Windows Firewall hoi, hay cho phep mang Private."
    Write-Host "Nhan Ctrl+Alt+M trong terminal nay de dung server."
    Start-Process $localUrl
    $awaitingStopKey = $false
    while ($true) {
        $key = [Console]::ReadKey($true)
        $controlPressed = ($key.Modifiers -band [ConsoleModifiers]::Control) -ne 0
        $altPressed = ($key.Modifiers -band [ConsoleModifiers]::Alt) -ne 0
        if ($controlPressed -and $altPressed -and $key.Key -eq [ConsoleKey]::M) {
            break
        }
    }
} finally {
    if ($server -and -not $server.HasExited) {
        Stop-Process -Id $server.Id
    }
}
