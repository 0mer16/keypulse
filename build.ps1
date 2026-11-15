# Builds dist\KeyPulse-<version>-win64.zip : KeyPulse.exe with OpenRGB bundled inside.
# Usage:  powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$OpenRGBVersion = "1.1"
$OpenRGBZipUrl  = "https://codeberg.org/OpenRGB/OpenRGB/releases/download/release_1.1/OpenRGB_1.1_Windows_64_8e16de2.zip"
$OpenRGBZipSha  = "63291726C6FC84EB479EF2EE752E97E1187F6CE9C49FD27EEE40DED588A8172A"
$OpenRGBSrcUrl  = "https://codeberg.org/OpenRGB/OpenRGB/archive/release_1.1.zip"
$OpenRGBLicUrl  = "https://codeberg.org/OpenRGB/OpenRGB/raw/tag/release_1.1/LICENSE"

$version = (python -c "import keypulse; print(keypulse.__version__)").Trim()
Write-Host "Building KeyPulse $version (OpenRGB $OpenRGBVersion)"

# 1. Fetch OpenRGB (pinned + checksum-verified)
$vendor = Join-Path $PSScriptRoot "vendor"
$orgbDir = Join-Path $vendor "OpenRGB"
New-Item -ItemType Directory -Force $vendor | Out-Null
if (-not (Test-Path (Join-Path $orgbDir "OpenRGB.exe"))) {
    $zip = Join-Path $vendor "openrgb.zip"
    curl.exe -sSL -o $zip $OpenRGBZipUrl
    $sha = (Get-FileHash $zip -Algorithm SHA256).Hash
    if ($sha -ne $OpenRGBZipSha) { throw "OpenRGB download checksum mismatch: $sha" }
    $tmp = Join-Path $vendor "x"
    Expand-Archive $zip -DestinationPath $tmp -Force
    Move-Item (Join-Path $tmp "OpenRGB Windows 64-bit") $orgbDir
    Remove-Item $tmp, $zip -Recurse -Force
}
if (-not (Test-Path (Join-Path $orgbDir "LICENSE.txt"))) {
    curl.exe -sSL -o (Join-Path $orgbDir "LICENSE.txt") $OpenRGBLicUrl
}
$srcZip = Join-Path $vendor "OpenRGB-$OpenRGBVersion-source.zip"
if (-not (Test-Path $srcZip)) { curl.exe -sSL -o $srcZip $OpenRGBSrcUrl }

# 2. Icon
python tools\make_icon.py

# 3. PyInstaller (one folder: fast start-up, OpenRGB sits next to the app)
python -m PyInstaller --noconfirm --clean --windowed --name KeyPulse `
    --icon keypulse\resources\icon.ico `
    --add-data "keypulse\resources;keypulse\resources" `
    --add-data "vendor\OpenRGB;OpenRGB" `
    --collect-data customtkinter `
    --distpath dist --workpath build `
    run.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

# 4. Docs + zip
Copy-Item README.md, LICENSE, THIRD_PARTY_NOTICES.md dist\KeyPulse\
$out = "dist\KeyPulse-$version-win64.zip"
if (Test-Path $out) { Remove-Item $out }
Compress-Archive -Path dist\KeyPulse -DestinationPath $out
Write-Host "Built $out  ($([math]::Round((Get-Item $out).Length / 1MB, 1)) MB)"
Write-Host "OpenRGB source for the release: $srcZip"
