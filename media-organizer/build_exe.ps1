# build_exe.ps1
# PowerShell script to build the media-organizer executable and output to a custom folder

$ErrorActionPreference = 'Stop'

# Set output directory
$outputDir = "build_output"

# Remove previous build if exists
if (Test-Path $outputDir) {
    Remove-Item $outputDir -Recurse -Force
}


# Run PyInstaller with the spec file in the project root
pyinstaller --distpath $outputDir --workpath .pyi_build --clean media_organizer.spec

Write-Host "Build complete. Output is in $outputDir\media-organizer.exe"
