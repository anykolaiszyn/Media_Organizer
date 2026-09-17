
# build_exe.ps1
# PowerShell script to build the media_organizer executable and output to a custom folder
# Run from the repository root: ./media_organizer/build_exe.ps1

# Deliberately not 'Stop': PyInstaller writes normal INFO-level progress to
# stderr, and PowerShell 5.1 treats a native command's stderr as a
# terminating error under $ErrorActionPreference = 'Stop' even on exit 0 --
# that combination previously made this script abort mid-build with no
# real failure. Removal failures below are still handled via explicit
# -ErrorAction Stop + try/catch, and a bad PyInstaller exit code is checked
# explicitly after the call.

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

# Run PyInstaller with the spec file in the project root.
# Invoked as "python -m PyInstaller" rather than the bare "pyinstaller"
# command, since the latter depends on its console-script shim being on
# PATH, which isn't guaranteed on every machine that has the package installed.
python -m PyInstaller --distpath $outputDir --workpath .pyi_build --clean media_organizer.spec
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller exited with code $LASTEXITCODE"
}

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
