$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$env:PYTHONUTF8 = '1'
Set-Location (Split-Path $PSScriptRoot -Parent)
try {
    if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64' -and $env:PROCESSOR_ARCHITEW6432 -ne 'AMD64') { throw 'This delivery targets Windows x64.' }
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($uv) { $uvPath = $uv.Source }
    else {
        $uvPath = Join-Path (Get-Location) 'runtime\uv\uv.exe'
        if (!(Test-Path $uvPath)) {
            Write-Host 'Preparing pinned uv Windows runtime (bundled archive or PyPI)...'
            $uvDir = Split-Path $uvPath -Parent
            New-Item -ItemType Directory -Force $uvDir | Out-Null
            $archive = Join-Path $uvDir 'uv-wheel.zip'
            $bundledUv = Join-Path (Get-Location) 'runtime\bootstrap\uv-wheel.zip'
            if (Test-Path $bundledUv) { Copy-Item $bundledUv $archive -Force }
            else {
                & curl.exe -fL --connect-timeout 15 --max-time 180 -o $archive 'https://files.pythonhosted.org/packages/c2/5d/8e0b84503b77ead843ef57e4f9305eb32a95cac6806c0e0d54b9404a5f7b/uv-0.12.19-py3-none-win_amd64.whl'
                if ($LASTEXITCODE -ne 0) { throw 'uv download failed. Check access to PyPI and rerun setup.' }
            }
            $expected = 'dcbc531a96762569bbfe9639b4f45f00aabff51f427540711f63e7c23f225fdf'
            if ((Get-FileHash $archive -Algorithm SHA256).Hash.ToLower() -ne $expected) { throw 'uv checksum mismatch.' }
            Expand-Archive $archive -DestinationPath $uvDir -Force
            $native = Get-ChildItem $uvDir -Filter uv.exe -Recurse | Select-Object -First 1
            if (!$native) { throw 'uv executable missing from official wheel.' }
            Copy-Item $native.FullName $uvPath -Force
        }
    }
    $python = '3.12.13'
    $localPython = Join-Path (Get-Location) 'runtime\python\python.exe'
    $bundledPython = Join-Path (Get-Location) 'runtime\bootstrap\python-windows.tar.gz'
    if (!(Test-Path $localPython) -and (Test-Path $bundledPython)) {
        if ((Get-FileHash $bundledPython -Algorithm SHA256).Hash.ToLower() -ne 'a814e8406b698ad491e1073717d644479e86abf34a3d5897b4d581381b4b8164') { throw 'Bundled Python checksum mismatch.' }
        & tar.exe -xzf $bundledPython -C (Join-Path (Get-Location) 'runtime')
        if ($LASTEXITCODE -ne 0) { throw 'Bundled Python could not be extracted.' }
    }
    if (Test-Path $localPython) {
        $version = & $localPython -c "import sys; print('.'.join(map(str,sys.version_info[:3])))"
        if ($version.Trim() -ne '3.12.13') { throw 'runtime/python must contain Python 3.12.13.' }
        $python = $localPython
    } else {
        $install = Start-Process -FilePath $uvPath -ArgumentList @('python','install','3.12.13') -NoNewWindow -PassThru
        if (!$install.WaitForExit(180000)) {
            & taskkill.exe /PID $install.Id /T /F | Out-Null
            throw 'Python download exceeded 3 minutes. Check network access, rerun setup, or provision the official runtime offline.'
        }
        $install.Refresh()
        if ($install.ExitCode -ne 0) { throw 'Python installation failed. Check download access or provision the official Python runtime offline.' }
    }
    & $uvPath sync --locked --python $python
    if ($LASTEXITCODE -ne 0) { throw 'Python dependencies could not be installed.' }
    if (!(Test-Path '.env')) { Copy-Item '.env.example' '.env'; Write-Host 'Created .env. Fill the service URLs and keys privately.' }
    & '.\.venv\Scripts\python.exe' -m doctransai.doctor --env-file '.env'
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Install LibreOffice Writer/Calc from https://www.libreoffice.org/download/download-libreoffice/'
        Write-Host 'Then run this setup again. Nonstandard paths: set DOCTRANSAI_SOFFICE in .env.'
        exit 1
    }
    $checkDir = 'outputs\setup-check-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
    & '.\.venv\Scripts\python.exe' -m doctransai.doctor --env-file '.env' --render-check $checkDir
    if ($LASTEXITCODE -ne 0) { throw 'Render self-check failed; inspect the error above.' }
    Write-Host "Inspect the PNG pages in $checkDir for Chinese fonts and layout."
    Write-Host 'Fill .env, then double-click start-windows.cmd. Keep that window open.'
} catch { Write-Host ('Setup failed: ' + $_.Exception.Message); exit 1 }
