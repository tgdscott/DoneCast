#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Real-time monitoring of local worker service status and resource usage
.DESCRIPTION
    Continuously polls the worker /status endpoint and displays:
    - Worker process CPU and memory usage
    - System-wide CPU and memory usage  
    - Active tasks being processed
    - Task duration
.PARAMETER Interval
    Seconds between status checks (default: 2)
.PARAMETER WorkerUrl
    Worker service URL (default: https://assemble.podcastplusplus.com)
.EXAMPLE
    .\scripts\monitor_worker.ps1
    .\scripts\monitor_worker.ps1 -Interval 5
#>

param(
    [int]$Interval = 2,
    [string]$WorkerUrl = "https://assemble.podcastplusplus.com"
)

$statusUrl = "$WorkerUrl/status"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Worker Monitoring Dashboard" -ForegroundColor Cyan
Write-Host "  URL: $WorkerUrl" -ForegroundColor Cyan
Write-Host "  Refresh: ${Interval}s" -ForegroundColor Cyan
Write-Host "  Press Ctrl+C to exit" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

function Format-Bytes {
    param([double]$bytes)
    if ($bytes -ge 1GB) { return "{0:N2} GB" -f ($bytes / 1GB) }
    if ($bytes -ge 1MB) { return "{0:N2} MB" -f ($bytes / 1MB) }
    if ($bytes -ge 1KB) { return "{0:N2} KB" -f ($bytes / 1KB) }
    return "$bytes B"
}

function Get-ColorForPercent {
    param([double]$percent)
    if ($percent -ge 90) { return "Red" }
    if ($percent -ge 70) { return "Yellow" }
    return "Green"
}

while ($true) {
    try {
        Clear-Host
        
        $response = Invoke-RestMethod -Uri $statusUrl -Method Get -ErrorAction Stop
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host "  Worker Status - $timestamp" -ForegroundColor Cyan
        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host ""
        
        # Status overview
        $statusColor = if ($response.status -eq "healthy") { "Green" } else { "Red" }
        Write-Host "Status: " -NoNewline
        Write-Host $response.status.ToUpper() -ForegroundColor $statusColor
        Write-Host "PID: $($response.pid)"
        Write-Host "Active Tasks: $($response.active_tasks)" -ForegroundColor $(if ($response.active_tasks -gt 0) { "Yellow" } else { "Gray" })
        Write-Host ""
        
        # Worker process stats
        Write-Host "Worker Process:" -ForegroundColor Cyan
        $workerCpu = $response.worker_process.cpu_percent
        $workerMem = $response.worker_process.memory_percent
        Write-Host "  CPU: " -NoNewline
        Write-Host "$workerCpu%" -ForegroundColor (Get-ColorForPercent $workerCpu)
        Write-Host "  Memory: " -NoNewline
        Write-Host "$($response.worker_process.memory_mb) MB ($workerMem%)" -ForegroundColor (Get-ColorForPercent $workerMem)
        Write-Host ""
        
        # System stats
        Write-Host "System (16GB Total):" -ForegroundColor Cyan
        $sysCpu = $response.system.cpu_percent
        $sysMem = $response.system.memory_percent
        Write-Host "  CPU: " -NoNewline
        Write-Host "$sysCpu%" -ForegroundColor (Get-ColorForPercent $sysCpu)
        Write-Host "  Memory: " -NoNewline
        Write-Host "$($response.system.memory_used_gb) GB / $($response.system.memory_total_gb) GB ($sysMem%)" -ForegroundColor (Get-ColorForPercent $sysMem)
        Write-Host ""
        
        # Active tasks
        if ($response.active_tasks -gt 0) {
            Write-Host "Active Tasks:" -ForegroundColor Yellow
            foreach ($taskId in $response.tasks.PSObject.Properties.Name) {
                $task = $response.tasks.$taskId
                $duration = [math]::Round($task.duration_seconds, 1)
                Write-Host "  [$($task.type)] Episode: $($task.episode_id)" -ForegroundColor Yellow
                Write-Host "    Running for: ${duration}s" -ForegroundColor Gray
                if ($task.chunk_id) {
                    Write-Host "    Chunk: $($task.chunk_id)" -ForegroundColor Gray
                }
            }
        } else {
            Write-Host "No active tasks - Idle" -ForegroundColor Gray
        }
        
        Write-Host ""
        Write-Host "Next refresh in ${Interval}s... (Ctrl+C to exit)" -ForegroundColor DarkGray
        
    } catch {
        Write-Host "ERROR: Failed to fetch worker status" -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor Red
        Write-Host ""
        Write-Host "Is the worker running? Check: $WorkerUrl/health" -ForegroundColor Yellow
    }
    
    Start-Sleep -Seconds $Interval
}
