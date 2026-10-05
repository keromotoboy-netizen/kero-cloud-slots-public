$ErrorActionPreference='Stop'
$Root='C:\ProgramData\Kero'
$Inbox=Join-Path $Root 'queue\inbox'
$Processing=Join-Path $Root 'queue\processing'
$Outbox=Join-Path $Root 'queue\outbox'
$Done=Join-Path $Root 'queue\done'
$Failed=Join-Path $Root 'queue\failed'
$Log=Join-Path $Root 'logs\agent.log'
@($Inbox,$Processing,$Outbox,$Done,$Failed,(Split-Path $Log)) | ForEach-Object { New-Item -ItemType Directory -Force -Path $_ | Out-Null }

$AllowedServices=@('sshd','Tailscale','KeroDeviceAgent','KeroWatchdog')

function Write-Log([string]$event,[hashtable]$detail=@{}) {
    $obj=[ordered]@{ts=(Get-Date).ToUniversalTime().ToString('o');event=$event;detail=$detail}
    Add-Content -Path $Log -Value ($obj|ConvertTo-Json -Compress -Depth 5)
}

function Emit-Result([string]$id,[string]$action,[bool]$ok,$data,$err) {
    $o=[ordered]@{
        id=$id; action=$action; ok=$ok
        ts=(Get-Date).ToUniversalTime().ToString('o')
        data=$data; error=$err
    }
    $tmp=Join-Path $Outbox ($id+'.json.tmp')
    $dst=Join-Path $Outbox ($id+'.json')
    $o|ConvertTo-Json -Compress -Depth 8|Set-Content -Encoding UTF8 -Path $tmp
    Move-Item -Force $tmp $dst
}

function Assert-ServiceAllowed([string]$name) {
    if($AllowedServices -notcontains $name){ throw "service_not_allowlisted" }
}

Write-Log 'agent_start' @{pid=$PID;identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name}

while($true) {
    try {
        $jobs=Get-ChildItem -Path $Inbox -Filter '*.json' -File -ErrorAction SilentlyContinue | Sort-Object CreationTimeUtc
        foreach($file in $jobs) {
            $proc=Join-Path $Processing $file.Name
            try { Move-Item -Path $file.FullName -Destination $proc -ErrorAction Stop } catch { continue }
            $job=$null
            try {
                $job=Get-Content -Raw -Path $proc | ConvertFrom-Json -ErrorAction Stop
                $id=[string]$job.id
                $action=[string]$job.action
                $risk=[int]$job.risk
                if($id -notmatch '^[A-Za-z0-9._:-]{8,128}$'){ throw 'bad_job_id' }
                if($risk -ge 3){ throw 'risk3_blocked' }
                if($job.expires_at){
                    $exp=[DateTimeOffset]::Parse([string]$job.expires_at)
                    if($exp -lt [DateTimeOffset]::UtcNow){ throw 'expired' }
                }
                $p=$job.params
                $data=$null
                switch($action) {
                    'status' {
                        if($risk -ne 1){throw 'risk_mismatch'}
                        $os=Get-CimInstance Win32_OperatingSystem
                        $cs=Get-CimInstance Win32_ComputerSystem
                        $data=[ordered]@{
                            host=$env:COMPUTERNAME
                            identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name
                            uptime_s=[int]((Get-Date)-$os.LastBootUpTime).TotalSeconds
                            ram_total_gb=[math]::Round($cs.TotalPhysicalMemory/1GB,1)
                            ram_free_gb=[math]::Round($os.FreePhysicalMemory*1KB/1GB,1)
                        }
                    }
                    'disk.status' {
                        if($risk -ne 1){throw 'risk_mismatch'}
                        $data=@(Get-PSDrive -PSProvider FileSystem | Select-Object Name,@{n='UsedGB';e={[math]::Round($_.Used/1GB,1)}},@{n='FreeGB';e={[math]::Round($_.Free/1GB,1)}})
                    }
                    'process.top' {
                        if($risk -ne 1){throw 'risk_mismatch'}
                        $data=@(Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 15 Name,Id,@{n='RAM_MB';e={[math]::Round($_.WorkingSet64/1MB,1)}},CPU)
                    }
                    'service.status' {
                        if($risk -ne 1){throw 'risk_mismatch'}
                        $name=[string]$p.service; Assert-ServiceAllowed $name
                        $data=Get-Service -Name $name -ErrorAction Stop | Select-Object Name,Status,StartType
                    }
                    'service.restart' {
                        if($risk -ne 2){throw 'risk_mismatch'}
                        $name=[string]$p.service; Assert-ServiceAllowed $name
                        Restart-Service -Name $name -ErrorAction Stop
                        $data=Get-Service -Name $name -ErrorAction Stop | Select-Object Name,Status,StartType
                    }
                    default { throw 'action_not_allowlisted' }
                }
                Emit-Result $id $action $true $data $null
                Move-Item -Force $proc (Join-Path $Done $file.Name)
                Write-Log 'job_ok' @{id=$id;action=$action}
            } catch {
                $id=if($job -and $job.id){[string]$job.id}else{[IO.Path]::GetFileNameWithoutExtension($file.Name)}
                $action=if($job -and $job.action){[string]$job.action}else{'unknown'}
                $msg=$_.Exception.Message
                if($msg.Length -gt 500){$msg=$msg.Substring(0,500)}
                Emit-Result $id $action $false $null $msg
                Move-Item -Force $proc (Join-Path $Failed $file.Name)
                Write-Log 'job_error' @{id=$id;action=$action;error=$msg}
            }
        }
    } catch {
        Write-Log 'loop_error' @{error=$_.Exception.Message}
    }
    Start-Sleep -Seconds 2
}
