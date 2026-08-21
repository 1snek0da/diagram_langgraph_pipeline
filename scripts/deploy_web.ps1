[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 4173,

    [string]$BindAddress = '127.0.0.1',

    [switch]$SkipBuild,

    [switch]$SkipMigrations,

    [switch]$OpenBrowser,

    [Parameter(DontShow)]
    [switch]$ServeOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-WebProjectRoot {
    param([string]$WorkspaceRoot)

    if (Test-Path -LiteralPath (Join-Path $WorkspaceRoot 'frontend\package.json')) {
        return $WorkspaceRoot
    }

    $previewRoot = Join-Path $WorkspaceRoot '.local\origin-main-preview'
    if (Test-Path -LiteralPath (Join-Path $previewRoot 'frontend\package.json')) {
        return $previewRoot
    }

    throw '找不到 frontend\package.json。请把脚本放在项目 scripts 目录，或保留 .local\origin-main-preview 工作树。'
}

function Resolve-PythonExecutable {
    param(
        [string]$WorkspaceRoot,
        [string]$ProjectRoot
    )

    $candidates = @(
        (Join-Path $WorkspaceRoot '.venv\Scripts\python.exe'),
        (Join-Path $ProjectRoot '.venv\Scripts\python.exe'),
        ([IO.Path]::GetFullPath((Join-Path $ProjectRoot '..\..\.venv\Scripts\python.exe')))
    ) | Select-Object -Unique

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    throw ('找不到 Python 虚拟环境。已检查：' + ($candidates -join '、'))
}

function Get-DotEnvValue {
    param(
        [string]$Path,
        [string]$Name
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ($line -match ('^\s*' + [regex]::Escape($Name) + '\s*=\s*(.*)\s*$')) {
            $value = $Matches[1].Trim()
            if (
                $value.Length -ge 2 -and
                (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                 ($value.StartsWith("'") -and $value.EndsWith("'")))
            ) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            return $value
        }
    }

    return $null
}

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$PortNumber,
        [int]$TimeoutMilliseconds = 1000
    )

    $client = [Net.Sockets.TcpClient]::new()
    try {
        $result = $client.BeginConnect($HostName, $PortNumber, $null, $null)
        if (-not $result.AsyncWaitHandle.WaitOne($TimeoutMilliseconds)) {
            return $false
        }
        $client.EndConnect($result)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Resolve-PostgresCtl {
    $command = Get-Command pg_ctl.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $installations = Get-ChildItem 'C:\Program Files\PostgreSQL\*\bin\pg_ctl.exe' -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending
    if ($installations) {
        return $installations[0].FullName
    }

    return $null
}

function Resolve-NodeExecutable {
    $command = Get-Command node.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        'C:\Program Files\nodejs\node.exe',
        (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe')
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    return $null
}

function Wait-ForHealth {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 60,
        [Diagnostics.Process]$Process
    )

    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process -and $Process.HasExited) {
            return $false
        }
        try {
            $response = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 3
            if ($null -ne $response) {
                return $true
            }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }

    return $false
}

$scriptDirectory = Split-Path -Parent $PSCommandPath
$workspaceRoot = Split-Path -Parent $scriptDirectory
$projectRoot = Resolve-WebProjectRoot -WorkspaceRoot $workspaceRoot
$pythonExecutable = Resolve-PythonExecutable -WorkspaceRoot $workspaceRoot -ProjectRoot $projectRoot
$frontendRoot = Join-Path $projectRoot 'frontend'
$frontendDist = Join-Path $frontendRoot 'dist'
$runtimeRoot = Join-Path $projectRoot '.local'
$runtimeLog = Join-Path $runtimeRoot ("web-{0}.log" -f $Port)
$pidFile = Join-Path $runtimeRoot ("web-{0}.pid" -f $Port)
$healthUrl = "http://${BindAddress}:${Port}/api/v1/health"
$siteUrl = "http://${BindAddress}:${Port}/"

New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null

$env:PYTHONPATH = Join-Path $projectRoot 'src'
$env:DLP_FRONTEND_DIST = $frontendDist

if ($ServeOnly) {
    Set-Location -LiteralPath $projectRoot
    "[$(Get-Date -Format o)] starting web service on $siteUrl" | Set-Content -LiteralPath $runtimeLog -Encoding UTF8
    & $pythonExecutable -m uvicorn diagram_langgraph_pipeline.api.app:create_app `
        --factory --host $BindAddress --port $Port *>> $runtimeLog
    exit $LASTEXITCODE
}

Set-Location -LiteralPath $projectRoot

$databaseUrl = Get-DotEnvValue -Path (Join-Path $projectRoot '.env.local') -Name 'DATABASE_URL'
if (-not $databaseUrl) {
    throw '缺少 DATABASE_URL。请先在 .env.local 中配置 PostgreSQL 连接。'
}

try {
    $databaseUri = [Uri]$databaseUrl
    $databaseHost = $databaseUri.Host
    $databasePort = if ($databaseUri.Port -gt 0) { $databaseUri.Port } else { 5432 }
} catch {
    throw 'DATABASE_URL 格式无效。'
}

if (-not (Test-TcpPort -HostName $databaseHost -PortNumber $databasePort)) {
    $localHosts = @('127.0.0.1', 'localhost', '::1')
    $postgresDataCandidates = @(
        (Join-Path $workspaceRoot '.local\postgres-data'),
        (Join-Path $projectRoot '.local\postgres-data')
    ) | Select-Object -Unique
    $postgresData = $postgresDataCandidates |
        Where-Object { Test-Path -LiteralPath (Join-Path $_ 'PG_VERSION') } |
        Select-Object -First 1

    if ($databaseHost -notin $localHosts -or -not $postgresData) {
        throw "PostgreSQL ${databaseHost}:${databasePort} 不可达，且没有可启动的本地数据目录。"
    }

    $pgCtl = Resolve-PostgresCtl
    if (-not $pgCtl) {
        throw '找不到 pg_ctl.exe；请安装 PostgreSQL 16 或把 PostgreSQL bin 目录加入 PATH。'
    }

    $postgresLog = Join-Path (Split-Path -Parent $postgresData) 'postgres.log'
    Write-Host "正在启动 PostgreSQL ${databaseHost}:${databasePort} ..."
    & $pgCtl start -D $postgresData -l $postgresLog -o "-p $databasePort" -w
    $pgCtlSucceeded = $LASTEXITCODE -eq 0

    if (-not $pgCtlSucceeded) {
        $postgresExecutable = Join-Path (Split-Path -Parent $pgCtl) 'postgres.exe'
        if (-not (Test-Path -LiteralPath $postgresExecutable)) {
            throw "PostgreSQL 启动失败，请查看日志：$postgresLog"
        }

        Write-Host 'pg_ctl 无法在当前会话启动服务，正在使用 postgres.exe 回退 ...'
        $postgresInfo = [Diagnostics.ProcessStartInfo]::new()
        $postgresInfo.FileName = $postgresExecutable
        $postgresInfo.Arguments = ('-D "{0}" -p {1}' -f $postgresData, $databasePort)
        $postgresInfo.WorkingDirectory = Split-Path -Parent $postgresExecutable
        $postgresInfo.UseShellExecute = $true
        $postgresInfo.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
        $postgresProcess = [Diagnostics.Process]::Start($postgresInfo)

        $databaseDeadline = [DateTime]::UtcNow.AddSeconds(30)
        while (
            [DateTime]::UtcNow -lt $databaseDeadline -and
            -not $postgresProcess.HasExited -and
            -not (Test-TcpPort -HostName $databaseHost -PortNumber $databasePort)
        ) {
            Start-Sleep -Milliseconds 500
        }
    }

    if (-not (Test-TcpPort -HostName $databaseHost -PortNumber $databasePort -TimeoutMilliseconds 3000)) {
        throw "PostgreSQL 启动失败，请查看日志：$postgresLog"
    }
}

if (-not $SkipMigrations) {
    Write-Host '正在检查数据库迁移 ...'
    & $pythonExecutable -m diagram_langgraph_pipeline init --yes
    if ($LASTEXITCODE -ne 0) {
        throw '数据库迁移失败。'
    }
}

if (-not $SkipBuild) {
    $vinextCommand = Join-Path $frontendRoot 'node_modules\.bin\vinext.cmd'
    $vinextCli = Join-Path $frontendRoot 'node_modules\vinext\dist\cli.js'
    if (-not (Test-Path -LiteralPath $vinextCommand)) {
        $pnpmCommand = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
        $npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
        Push-Location $frontendRoot
        try {
            if ($pnpmCommand) {
                Write-Host '正在安装前端依赖 ...'
                & $pnpmCommand.Source install --frozen-lockfile
            } elseif ($npmCommand) {
                Write-Host '正在安装前端依赖 ...'
                & $npmCommand.Source ci
            } else {
                throw '找不到 pnpm.cmd 或 npm.cmd，无法安装前端依赖。'
            }
            if ($LASTEXITCODE -ne 0) {
                throw '前端依赖安装失败。'
            }
        } finally {
            Pop-Location
        }
    }

    $nodeExecutable = Resolve-NodeExecutable
    if (-not $nodeExecutable) {
        throw '找不到 node.exe；请安装 Node.js 22.13 或更高版本。'
    }
    if (-not (Test-Path -LiteralPath $vinextCli)) {
        throw "找不到 Vinext 构建入口：$vinextCli"
    }

    Write-Host '正在构建前端 ...'
    Push-Location $frontendRoot
    try {
        $env:WRANGLER_LOG_PATH = Join-Path $frontendRoot '.wrangler\wrangler.log'
        & $nodeExecutable $vinextCli build
        if ($LASTEXITCODE -ne 0) {
            throw '前端构建失败。'
        }
    } finally {
        Pop-Location
    }
}

$frontendEntry = Join-Path $frontendDist 'client\index.html'
if (-not (Test-Path -LiteralPath $frontendEntry)) {
    throw "找不到构建产物：$frontendEntry。请去掉 -SkipBuild 后重试。"
}

if (Wait-ForHealth -Url $healthUrl -TimeoutSeconds 2) {
    Write-Host "网站已经运行：$siteUrl" -ForegroundColor Green
    if ($OpenBrowser) {
        Start-Process $siteUrl
    }
    exit 0
}

if (Test-TcpPort -HostName $BindAddress -PortNumber $Port) {
    throw "端口 $Port 已被其他程序占用，且该程序不是本项目 API。请改用 -Port 指定其他端口。"
}

$hostExecutable = if (Test-Path -LiteralPath (Join-Path $PSHOME 'pwsh.exe')) {
    Join-Path $PSHOME 'pwsh.exe'
} else {
    (Get-Command powershell.exe -ErrorAction Stop).Source
}

$processInfo = [Diagnostics.ProcessStartInfo]::new()
$processInfo.FileName = $hostExecutable
$processInfo.Arguments = (
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "{0}" -ServeOnly -Port {1} -BindAddress "{2}"' -f
    $PSCommandPath, $Port, $BindAddress
)
$processInfo.WorkingDirectory = $projectRoot
$processInfo.UseShellExecute = $true
$processInfo.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
$webProcess = [Diagnostics.Process]::Start($processInfo)

Write-Host '正在等待网站服务就绪 ...'
if (-not (Wait-ForHealth -Url $healthUrl -TimeoutSeconds 90 -Process $webProcess)) {
    $logTail = if (Test-Path -LiteralPath $runtimeLog) {
        (Get-Content -LiteralPath $runtimeLog -Tail 30) -join [Environment]::NewLine
    } else {
        '未生成运行日志。'
    }
    throw "网站启动失败。运行日志：`n$logTail"
}

$listenerPid = $null
try {
    $listenerPid = (Get-NetTCPConnection -LocalAddress $BindAddress -LocalPort $Port -State Listen -ErrorAction Stop |
        Select-Object -First 1 -ExpandProperty OwningProcess)
} catch {
    $listenerPid = $webProcess.Id
}
$listenerPid | Set-Content -LiteralPath $pidFile -Encoding ASCII

Write-Host "部署完成：$siteUrl" -ForegroundColor Green
Write-Host "健康检查：$healthUrl"
Write-Host "运行日志：$runtimeLog"

if ($OpenBrowser) {
    Start-Process $siteUrl
}
