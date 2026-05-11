$ContainerName = "finally-app"

$running = docker ps -q -f "name=^${ContainerName}$" 2>$null
$stopped = docker ps -aq -f "name=^${ContainerName}$" 2>$null

if ($running) {
    Write-Host "Stopping FinAlly..."
    docker stop $ContainerName
    docker rm $ContainerName
    Write-Host "FinAlly stopped. Database data preserved in .\db\"
} elseif ($stopped) {
    docker rm $ContainerName
    Write-Host "Removed stopped container."
} else {
    Write-Host "FinAlly is not running."
}
