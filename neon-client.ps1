# Neon Uploader Windows 11 x64 launcher. Native Pi file explorer by default, Opera GX with -Opera.
# First use: .\neon-client.ps1 -Setup
# Optional automatic Windows sign-in: .\neon-client.ps1 -InstallStartup
param(
    [switch]$Setup,
    [switch]$InstallStartup,
    [switch]$RemoveStartup,
    [switch]$Opera,
    [switch]$Browse
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Find-OperaGX {
    $paths = @()
    if ($env:LOCALAPPDATA) {
        $paths += (Join-Path $env:LOCALAPPDATA 'Programs\Opera GX\launcher.exe')
        $paths += (Join-Path $env:LOCALAPPDATA 'Programs\Opera GX\opera.exe')
    }
    if ($env:ProgramFiles) {
        $paths += (Join-Path $env:ProgramFiles 'Opera GX\launcher.exe')
        $paths += (Join-Path $env:ProgramFiles 'Opera GX\opera.exe')
    }
    ${programFilesX86} = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
    if (${programFilesX86}) {
        $paths += (Join-Path ${programFilesX86} 'Opera GX\launcher.exe')
        $paths += (Join-Path ${programFilesX86} 'Opera GX\opera.exe')
    }
    foreach ($path in $paths) {
        if (Test-Path -LiteralPath $path -PathType Leaf) { return $path }
    }
    return $null
}

function Validate-ServerUrl([string]$value) {
    $uri = $null
    if (-not [Uri]::TryCreate($value, [UriKind]::Absolute, [ref]$uri)) {
        throw 'Enter the complete Pi URL, such as http://192.168.1.50:8080'
    }
    if ($uri.Scheme -notin @('http','https') -or -not $uri.Host -or
        $uri.UserInfo -or $uri.AbsolutePath -ne '/' -or $uri.Query -or $uri.Fragment) {
        throw 'Use an http:// or https:// origin with no path, username, password, query or fragment.'
    }
    return $uri.GetLeftPart([UriPartial]::Authority).TrimEnd('/')
}

$settings = Join-Path $env:APPDATA 'NeonUploader'
$uriFile = Join-Path $settings 'pi-url.txt'
$credentialFile = Join-Path $settings 'credential.xml'
$startupDir = [Environment]::GetFolderPath('Startup')
$startupLink = Join-Path $startupDir 'Neon Uploader Client.lnk'
$batch = Join-Path $PSScriptRoot 'neon-client.bat'

if ($RemoveStartup) {
    Remove-Item -LiteralPath $startupLink -ErrorAction SilentlyContinue
    Write-Host '[neon] Windows startup auto-login disabled.'
    exit 0
}

if ($InstallStartup) {
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($startupLink)
    $link.TargetPath = $batch
    $link.WorkingDirectory = $PSScriptRoot
    $link.Arguments = '-Opera'  # Preserve original Opera GX auto-login at Windows sign-in.
    $link.Description = 'Sign in to the Raspberry Pi Neon Uploader using Opera GX'
    $link.Save()
    Write-Host '[neon] Enabled automatic login on Windows user sign-in.'
    Write-Host '[neon] Keep these client files in this folder; the startup shortcut uses this path.'
    # Continue into the normal first-run setup and open Opera GX now.
}

if ($Setup -or -not (Test-Path -LiteralPath $uriFile) -or
    -not (Test-Path -LiteralPath $credentialFile)) {
    New-Item -ItemType Directory -Path $settings -Force | Out-Null
    $example = 'http://192.168.1.50:8080'
    if (Test-Path -LiteralPath $uriFile) { $example = (Get-Content -LiteralPath $uriFile -Raw).Trim() }
    $entry = Read-Host "Raspberry Pi Neon URL [$example]"
    if (-not $entry) { $entry = $example }
    $baseUrl = Validate-ServerUrl $entry
    if ($baseUrl.StartsWith('http://')) {
        Write-Warning 'HTTP transmits the authentication password without encryption. Only use it on a trusted local network, preferably behind a VPN or HTTPS proxy.'
        $allow = Read-Host 'Continue over HTTP? [y/N]'
        if ($allow -notin @('y','Y','yes','YES')) { throw 'Setup cancelled. Use an HTTPS URL if possible.' }
    }
    Write-Host 'Enter the password printed on the Pi server console. Username must be neon.'
    $credential = Get-Credential -UserName 'neon' -Message 'Neon Uploader Raspberry Pi login'
    if (-not $credential -or $credential.UserName -ne 'neon') {
        throw 'Authentication setup cancelled or username differs from neon.'
    }
    # Export-Clixml uses Windows DPAPI, bound to the current Windows user.
    $credential | Export-Clixml -LiteralPath $credentialFile
    Set-Content -LiteralPath $uriFile -Value $baseUrl -Encoding ASCII
    Write-Host '[neon] Credentials saved encrypted for this Windows user.'
}

$baseUrl = Validate-ServerUrl ((Get-Content -LiteralPath $uriFile -Raw).Trim())
$credential = Import-Clixml -LiteralPath $credentialFile
if ($credential -isnot [System.Management.Automation.PSCredential] -or $credential.UserName -ne 'neon') {
    throw 'Saved credentials are invalid. Run neon-client.bat -Setup to configure again.'
}

# The default Windows client is a native file explorer, not merely a login shortcut.
# Use -Opera to open the web application with one-use automatic authentication.
if ($Opera -and $Browse) { throw 'Choose -Browse or -Opera, not both.' }
if (-not $Opera) {
    $browser = Join-Path $PSScriptRoot 'neon-browser.ps1'
    if (-not (Test-Path -LiteralPath $browser)) {
        throw 'Missing neon-browser.ps1. Update both Windows client scripts from GitHub.'
    }
    & $browser
    return
}

# Obtain a one-time browser ticket from the Pi. Never put the persistent
# password into Opera's command line, address bar, history or a URL.
$plainPassword = $credential.GetNetworkCredential().Password
$basic = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes('neon:' + $plainPassword))
$plainPassword = $null
try {
    $response = Invoke-RestMethod -Uri ($baseUrl + '/api/auth/ticket') -Method Post `
        -Headers @{ Authorization = ('Basic ' + $basic) } `
        -ContentType 'application/json' -Body '{}' -TimeoutSec 12
} catch {
    throw "Could not obtain Pi login ticket. Check the Pi IP, port and password. For a new password, run neon-client.bat -Setup. Details: $($_.Exception.Message)"
} finally {
    $basic = $null
}

if (-not $response.ticket) { throw 'Pi server did not return a login ticket. Update the Pi server to this version.' }
# Fragment (after #) never travels in the HTTP request or normal server logs.
$loginUrl = $baseUrl + '/__neon_login#ticket=' + [Uri]::EscapeDataString([string]$response.ticket)
$opera = Find-OperaGX
if ($opera) {
    Start-Process -FilePath $opera -ArgumentList ('"' + $loginUrl + '"')
    Write-Host '[neon] Opened Opera GX and initiated automatic Pi login.'
} else {
    Start-Process $loginUrl
    Write-Host '[neon] Opera GX not found; opened the default browser instead.'
}
