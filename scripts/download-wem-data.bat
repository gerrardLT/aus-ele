@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion
title WEM Data Download Tool

echo ============================================================
echo   WEM (Western Australian Electricity Market) Data Download
echo   WEM (Xi Ao Dian Li Shi Chang) Li Shi Shu Ju Xia Zai
echo ============================================================
echo.
echo   Source: AEMO public file server (no registration needed)
echo   Range : 2023-10-01 to present
echo   Content:
echo     - Dispatch Solution (ESS prices+capacity+constraints, ~285MB/day)
echo     - Reference Trading Price (30-min RTP, ~1KB/day)
echo.
echo   NOTE: Full Dispatch Solution is ~260GB, download takes a long time.
echo         Supports resume. Re-run after interruption to continue.
echo.
echo ============================================================
echo.

:: Check curl availability
where curl >nul 2>&1
if errorlevel 1 (
    echo [ERROR] curl not found. Requires Windows 10 1803+ or manual curl install.
    pause
    exit /b 1
)

:: Select download directory
set "DEFAULT_DIR=%USERPROFILE%\Desktop\wem_raw_data"
echo Enter download directory (press Enter for default):
echo   Default: %DEFAULT_DIR%
echo.
set /p "DOWNLOAD_DIR=Directory: "
if "!DOWNLOAD_DIR!"=="" set "DOWNLOAD_DIR=%DEFAULT_DIR%"

:: Create directories
if not exist "!DOWNLOAD_DIR!" mkdir "!DOWNLOAD_DIR!"
if not exist "!DOWNLOAD_DIR!\dispatch_solution" mkdir "!DOWNLOAD_DIR!\dispatch_solution"
if not exist "!DOWNLOAD_DIR!\reference_trading_price" mkdir "!DOWNLOAD_DIR!\reference_trading_price"

echo.
echo Download directory: !DOWNLOAD_DIR!
echo.

:: Select download mode
echo Select download mode:
echo   [1] RTP price data only (fast, ~50MB total, a few minutes)
echo   [2] Dispatch Solution only (large, ~260GB total)
echo   [3] Download all (RTP + Dispatch Solution)
echo   [4] Custom date range
echo   [5] Exit
echo.
set /p "MODE=Enter option (1-5): "

if "!MODE!"=="5" goto :end
if "!MODE!"=="4" goto :custom_range

:: Set default date range
set "START_DATE=2023-10-01"
:: Get yesterday's date
for /f %%i in ('powershell -NoProfile -Command "[datetime]::Now.AddDays(-1).ToString(\"yyyy-MM-dd\")"') do set "END_DATE=%%i"
if "!END_DATE!"=="" set "END_DATE=2026-05-18"

goto :start_download

:custom_range
echo.
set /p "START_DATE=Start date (YYYY-MM-DD, earliest 2023-10-01): "
set /p "END_DATE=End date (YYYY-MM-DD): "
echo.
echo Select content:
echo   [1] RTP price data only
echo   [2] Dispatch Solution only
echo   [3] Download all
set /p "MODE=Enter option (1-3): "

:start_download
echo.
echo ============================================================
echo Starting download...
echo Date range: !START_DATE! to !END_DATE!
echo ============================================================
echo.

:: Download FCESS facility capabilities
echo [0] Downloading FCESS facility capabilities...
curl -k -s -L -o "!DOWNLOAD_DIR!\fcess_capabilities.csv" "https://data.wa.aemo.com.au/public/public-data/datafiles/fcess/fcess.csv"
if exist "!DOWNLOAD_DIR!\fcess_capabilities.csv" (
    echo     Done!
) else (
    echo     Failed (non-critical, continuing...)
)
echo.

:: Route based on mode
if "!MODE!"=="2" goto :download_dispatch
if "!MODE!"=="1" goto :download_rtp
:: MODE==3: download RTP first, then Dispatch

:download_rtp
echo --- Downloading RTP Price Data ---
echo.

:: Generate date list via PowerShell
set "DATE_LIST=!DOWNLOAD_DIR!\__dates_rtp.tmp"
powershell -NoProfile -Command ^
    "$s=[datetime]::ParseExact('!START_DATE!','yyyy-MM-dd',$null);$e=[datetime]::ParseExact('!END_DATE!','yyyy-MM-dd',$null);$c=$s;while($c -le $e){$c.ToString('yyyyMMdd');$c=$c.AddDays(1)}" > "!DATE_LIST!"

set /a "RTP_OK=0"
set /a "RTP_SKIP=0"
set /a "RTP_FAIL=0"
set /a "RTP_COUNT=0"

for /f %%d in ('type "!DATE_LIST!"') do (
    set /a "RTP_COUNT+=1"
    set "FNAME=ReferenceTradingPrice_%%d.zip"
    set "FPATH=!DOWNLOAD_DIR!\reference_trading_price\!FNAME!"
    set "FURL=https://data.wa.aemo.com.au/public/market-data/wemde/referenceTradingPrice/previous/!FNAME!"

    if exist "!FPATH!" (
        set /a "RTP_SKIP+=1"
    ) else (
        echo [!RTP_COUNT!] !FNAME!
        curl -k -s -L -o "!FPATH!" "!FURL!"
        if exist "!FPATH!" (
            set /a "RTP_OK+=1"
        ) else (
            set /a "RTP_FAIL+=1"
        )
    )
)

del "!DATE_LIST!" 2>nul
echo.
echo RTP done: !RTP_OK! success, !RTP_SKIP! skipped, !RTP_FAIL! failed
echo.

if "!MODE!"=="1" goto :done
if "!MODE!"=="3" goto :download_dispatch
goto :done

:download_dispatch
echo --- Downloading Dispatch Solution ---
echo (Each file ~285MB, supports resume, please be patient)
echo.

:: Generate date list
set "DATE_LIST=!DOWNLOAD_DIR!\__dates_dispatch.tmp"
powershell -NoProfile -Command ^
    "$s=[datetime]::ParseExact('!START_DATE!','yyyy-MM-dd',$null);$e=[datetime]::ParseExact('!END_DATE!','yyyy-MM-dd',$null);$c=$s;while($c -le $e){$c.ToString('yyyyMMdd');$c=$c.AddDays(1)}" > "!DATE_LIST!"

set /a "DS_OK=0"
set /a "DS_SKIP=0"
set /a "DS_FAIL=0"
set /a "DS_COUNT=0"

for /f %%d in ('type "!DATE_LIST!"') do (
    set /a "DS_COUNT+=1"
    set "FNAME=DispatchSolutionReference_%%d.zip"
    set "FPATH=!DOWNLOAD_DIR!\dispatch_solution\!FNAME!"
    set "FURL=https://data.wa.aemo.com.au/public/market-data/wemde/dispatchSolution/dispatchData/previous/!FNAME!"

    :: Skip files that appear complete (>100MB)
    set "SKIP_THIS=0"
    if exist "!FPATH!" (
        for %%f in ("!FPATH!") do (
            if %%~zf GTR 100000000 set "SKIP_THIS=1"
        )
    )

    if "!SKIP_THIS!"=="1" (
        set /a "DS_SKIP+=1"
        echo [!DS_COUNT!] !FNAME! - exists, skipping
    ) else (
        echo [!DS_COUNT!] !FNAME! - downloading...
        :: curl -C - supports resume, -# shows progress bar
        curl -k -C - -L -# -o "!FPATH!" "!FURL!"
        if !errorlevel! EQU 0 (
            set /a "DS_OK+=1"
        ) else (
            echo     [WARN] Download may be incomplete, will auto-resume next run
            set /a "DS_FAIL+=1"
        )
        :: 1 second delay to avoid rate limiting
        timeout /t 1 /nobreak >nul
    )
)

del "!DATE_LIST!" 2>nul
echo.
echo Dispatch Solution done: !DS_OK! success, !DS_SKIP! skipped, !DS_FAIL! failed
echo.

:done
echo.
echo ============================================================
echo Download complete!
echo Data saved to: !DOWNLOAD_DIR!
echo.
echo Directory structure:
echo   !DOWNLOAD_DIR!\dispatch_solution\      (ESS dispatch solutions)
echo   !DOWNLOAD_DIR!\reference_trading_price\ (RTP prices)
echo   !DOWNLOAD_DIR!\fcess_capabilities.csv   (facility capabilities)
echo.
echo To import into database, run:
echo   python scrapers/aemo_wem_ess_scraper.py --start !START_DATE! --end !END_DATE!
echo ============================================================
echo.

:end
endlocal
pause
