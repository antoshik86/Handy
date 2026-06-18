param(
    [switch]$Force
)
$ModelDir = "$env:USERPROFILE\.vosk\vosk-model-small-ru-0.22"
$ZipPath = "$env:USERPROFILE\.vosk\vosk-model-small-ru-0.22.zip"

if ((Test-Path $ModelDir) -and !$Force) {
    Write-Output "Model already exists at $ModelDir"
    exit 0
}

New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.vosk" | Out-Null
Write-Output "Downloading Vosk Russian model (46MB)..."
Start-BitsTransfer -Source "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip" `
    -Destination $ZipPath -Description "Vosk Russian Model"
Write-Output "Extracting..."
Expand-Archive -Path $ZipPath -DestinationPath "$env:USERPROFILE\.vosk" -Force
Remove-Item $ZipPath
Write-Output "Done: $ModelDir"
