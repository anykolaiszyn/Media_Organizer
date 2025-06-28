
# build_exe.ps1
# PowerShell script to build the media_organizer executable and output to a custom folder

$ErrorActionPreference = 'Stop'

# Set output directory
$outputDir = "build_output"


# Remove previous build if exists, retry if locked
function Remove-BuildOutput {
    param([string]$dir)
    $maxTries = 5
    $waitSec = 2
    $try = 0
    while ($try -lt $maxTries) {
        if (Test-Path $dir) {
            try {
                Remove-Item $dir -Recurse -Force -ErrorAction Stop
                if (-not (Test-Path $dir)) {
                    break
                }
            } catch {
                Write-Warning "Could not remove $dir (try $($try+1)/$maxTries): $_.Exception.Message"
                Start-Sleep -Seconds $waitSec
            }
        } else {
            break
        }
        $try++
    }
    if (Test-Path $dir) {
        throw "Failed to remove $dir after $maxTries attempts. Please close any programs using it and try again."
    }
}
Remove-BuildOutput $outputDir

# Run PyInstaller with the spec file in the project root
pyinstaller --distpath $outputDir --workpath .pyi_build --clean media_organizer.spec

# Copy the entire ExifTool folder (including all DLLs, Perl files, and subfolders) to the output directory
$exiftoolFolderSource = Join-Path $PSScriptRoot "ExifTool"
$exiftoolFolderDest = Join-Path $outputDir "ExifTool"
if (Test-Path $exiftoolFolderSource) {
    if (Test-Path $exiftoolFolderDest) {
        Remove-Item $exiftoolFolderDest -Recurse -Force
    }
    Copy-Item $exiftoolFolderSource $outputDir -Recurse -Force
    Write-Host "Copied ExifTool folder to $outputDir."
} else {
    Write-Warning "ExifTool folder not found at $exiftoolFolderSource. You must copy it manually."
}

Write-Host "Build complete. Output is in $outputDir\media_organizer.exe"
