param([switch]$Build)
$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectDir

$ImageName = "finally"
$ContainerName = "finally-app"

try {
    # Build if needed
    $imageExists = docker image inspect $ImageName 2>$null
    $shouldBuild = $Build -or (-not $imageExists)
    if ($shouldBuild) {
        Write-Host "Building FinAlly Docker image..."
        docker build -t $ImageName .
    }

    # Stop existing container
    $running = docker ps -q -f "name=^${ContainerName}$" 2>$null
    $stopped = docker ps -aq -f "name=^${ContainerName}$" 2>$null
    if ($running) {
        Write-Host "Stopping existing container..."
        docker stop $ContainerName | Out-Null
        docker rm $ContainerName | Out-Null
    } elseif ($stopped) {
        docker rm $ContainerName | Out-Null
    }

    # Ensure db directory
    New-Item -ItemType Directory -Force -Path db | Out-Null

    Write-Host "Starting FinAlly..."
    docker run -d `
        --name $ContainerName `
        -p 8000:8000 `
        -v "${PWD}\db:/app/db" `
        --env-file .env `
        --restart unless-stopped `
        $ImageName

    Write-Host ""
    Write-Host "FinAlly is starting at: http://localhost:8000"
    Write-Host "  To stop:      .\scripts\stop_windows.ps1"
    Write-Host "  To view logs: docker logs -f $ContainerName"
    Write-Host "  To rebuild:   .\scripts\start_windows.ps1 -Build"
    Write-Host ""

    Start-Sleep -Seconds 3
    Start-Process "http://localhost:8000"
} finally {
    Pop-Location
}
