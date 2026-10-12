param(
    [ValidateSet('All', 'Main', 'Upgrade')]
    [string]$Mode = 'All',
    [string]$PythonExe = 'D:\Miniconda\envs\TTUD\python.exe',
    [switch]$Resume,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$mainOutput = Join-Path $projectRoot 'results\benchmark_report_01'
$studyOutput = Join-Path $projectRoot 'results\high_score_upgrade_20261010'

function Invoke-ProjectPython {
    param([string[]]$Arguments)
    Write-Host ('python ' + ($Arguments -join ' '))
    & $PythonExe -X utf8 @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE. Later stages were not started."
    }
}

if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Python interpreter not found: $PythonExe"
}

Push-Location -LiteralPath $projectRoot
try {
    if ($CheckOnly) {
        Invoke-ProjectPython -Arguments @('-m', 'src', 'benchmark', '--config', 'configs/benchmark.json',
            '--preset', 'report', '--groups', 'maps', 'scalability', 'kris', '--dry-run')
        Write-Host 'Check passed. No solver was run and no results directory was created.'
        return
    }

    # Check both destinations before starting a long run.
    foreach ($destination in @($mainOutput, $studyOutput)) {
        $selected = ($Mode -eq 'All') -or
            (($Mode -eq 'Main') -and ($destination -eq $mainOutput)) -or
            (($Mode -eq 'Upgrade') -and ($destination -eq $studyOutput))
        if ($selected -and (Test-Path -LiteralPath $destination) -and
            (@(Get-ChildItem -LiteralPath $destination -Force).Count -gt 0) -and (-not $Resume)) {
            throw "Output already contains evidence: $destination. Use -Resume to audit and continue it."
        }
    }

    if ($Mode -in @('All', 'Main')) {
        $mainArguments = @('-m', 'src', 'benchmark', '--config', 'configs/benchmark.json',
            '--preset', 'report', '--groups', 'maps', 'scalability', 'kris',
            '--output', 'results/benchmark_report_01', '--presentation')
        if ($Resume) { $mainArguments += '--resume' }
        Invoke-ProjectPython -Arguments $mainArguments
        Write-Host 'Main benchmark gallery: results/benchmark_report_01/report/index.html'
    }

    if ($Mode -in @('All', 'Upgrade')) {
        if (-not (Test-Path -LiteralPath (Join-Path $studyOutput 'protocol.lock.json'))) {
            Invoke-ProjectPython -Arguments @('scripts/run_upgrade_study.py', 'prepare')
        }
        Invoke-ProjectPython -Arguments @('scripts/upgrade_study_driver.py', 'pilot')
        Invoke-ProjectPython -Arguments @('scripts/upgrade_study_driver.py', 'holdout')
        Invoke-ProjectPython -Arguments @('scripts/upgrade_study_driver.py', 'verify')

        foreach ($audit in @(
            @{ Directory = 'tiny_exact'; Script = 'report/upgrade_exact.py' },
            @{ Directory = 'tiny_branch'; Script = 'report/upgrade_branch_audit.py' }
        )) {
            $auditDirectory = Join-Path $studyOutput $audit.Directory
            $auditArguments = @($audit.Script)
            if (Test-Path -LiteralPath $auditDirectory) { $auditArguments += '--verify' }
            Invoke-ProjectPython -Arguments $auditArguments
        }
        Invoke-ProjectPython -Arguments @('report/analyze_upgrade.py')
        Write-Host 'Upgrade figures: report/image/upgrade'
        Write-Host 'Upgrade tables and analysis: report/generated/upgrade'
    }

    Write-Host 'Finished. The existing report/main.pdf and report.zip still need updating from the new results.'
}
finally {
    Pop-Location
}
