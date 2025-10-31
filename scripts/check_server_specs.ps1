# Server Specs Diagnostic Script
# Run this on your server to gather hardware info

Write-Host "=== PODCAST PLUS PLUS SERVER DIAGNOSTIC ===" -ForegroundColor Cyan
Write-Host ""

# CPU Info
Write-Host "--- CPU ---" -ForegroundColor Yellow
Get-WmiObject Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed | Format-List

# Memory Info
Write-Host "--- MEMORY ---" -ForegroundColor Yellow
$mem = Get-WmiObject Win32_ComputerSystem
$totalRAM = [math]::Round($mem.TotalPhysicalMemory / 1GB, 2)
Write-Host "Total RAM: $totalRAM GB"
Write-Host ""

# Disk Info
Write-Host "--- STORAGE ---" -ForegroundColor Yellow
Get-WmiObject Win32_LogicalDisk -Filter "DriveType=3" | Select-Object DeviceID, 
    @{Name="Size(GB)";Expression={[math]::Round($_.Size / 1GB, 2)}}, 
    @{Name="FreeSpace(GB)";Expression={[math]::Round($_.FreeSpace / 1GB, 2)}},
    @{Name="PercentFree";Expression={[math]::Round(($_.FreeSpace / $_.Size) * 100, 2)}} | Format-Table -AutoSize

# Network Info
Write-Host "--- NETWORK ---" -ForegroundColor Yellow
Get-NetAdapter | Where-Object Status -eq "Up" | Select-Object Name, InterfaceDescription, LinkSpeed | Format-Table -AutoSize

# OS Info
Write-Host "--- OPERATING SYSTEM ---" -ForegroundColor Yellow
Get-WmiObject Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber, OSArchitecture | Format-List

# Check for Docker
Write-Host "--- DOCKER STATUS ---" -ForegroundColor Yellow
try {
    docker --version
    Write-Host "Docker installed: YES" -ForegroundColor Green
} catch {
    Write-Host "Docker installed: NO" -ForegroundColor Red
}
Write-Host ""

# Check for Python
Write-Host "--- PYTHON STATUS ---" -ForegroundColor Yellow
try {
    python --version
    Write-Host "Python installed: YES" -ForegroundColor Green
} catch {
    Write-Host "Python installed: NO" -ForegroundColor Red
}
Write-Host ""

# RAID Controller Check (if available)
Write-Host "--- RAID CONTROLLER ---" -ForegroundColor Yellow
$raid = Get-WmiObject -Namespace root\wmi -Class MSStorageDriver_FailurePredictStatus -ErrorAction SilentlyContinue
if ($raid) {
    Write-Host "RAID controller detected (check hardware manufacturer tools for detailed status)"
} else {
    Write-Host "No RAID controller detected via WMI (may need manufacturer-specific tools)"
    Write-Host "NOTE: RAID is NOT required for operation - just provides redundancy" -ForegroundColor Cyan
}
Write-Host ""

# Disk Health (SMART status)
Write-Host "--- DISK HEALTH ---" -ForegroundColor Yellow
try {
    $disks = Get-PhysicalDisk
    foreach ($disk in $disks) {
        $health = $disk.HealthStatus
        $usage = $disk.Usage
        $size = [math]::Round($disk.Size / 1GB, 2)
        
        $color = "Green"
        if ($health -ne "Healthy") { $color = "Red" }
        
        Write-Host "Disk $($disk.DeviceId): $size GB - $usage - Health: $health" -ForegroundColor $color
    }
} catch {
    Write-Host "Could not retrieve disk health info (may need admin privileges)"
}
Write-Host ""

Write-Host "=== END DIAGNOSTIC ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "NEXT STEPS:" -ForegroundColor Green
Write-Host "1. Take a screenshot of this output"
Write-Host "2. Check RAID controller status with manufacturer tools (Dell OpenManage, HP Smart Storage, etc.)"
Write-Host "3. Share with Scott for architecture planning"
