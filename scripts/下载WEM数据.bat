@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion
title WEM 数据下载工具

echo ============================================================
echo   WEM (西澳电力市场) 历史数据下载工具
echo ============================================================
echo.
echo   数据来源: AEMO 公开文件服务器 (无需注册)
echo   数据范围: 2023-10-01 至今
echo   包含内容:
echo     - Dispatch Solution (ESS价格+容量+约束, 每天约285MB)
echo     - Reference Trading Price (30分钟电价, 每天约1KB)
echo.
echo   注意: Dispatch Solution 全量约 260GB, 下载需要较长时间
echo         支持断点续传, 中断后重新运行即可继续
echo.
echo ============================================================
echo.

:: 检查 curl 是否可用
where curl >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 curl 命令。请确保 Windows 10 1803+ 或手动安装 curl。
    pause
    exit /b 1
)

:: 选择下载目录
set "DEFAULT_DIR=%USERPROFILE%\Desktop\wem_raw_data"
echo 请输入下载目录 (直接回车使用默认目录):
echo   默认: %DEFAULT_DIR%
echo.
set /p "DOWNLOAD_DIR=下载目录: "
if "!DOWNLOAD_DIR!"=="" set "DOWNLOAD_DIR=%DEFAULT_DIR%"

:: 创建目录
if not exist "!DOWNLOAD_DIR!" mkdir "!DOWNLOAD_DIR!"
if not exist "!DOWNLOAD_DIR!\dispatch_solution" mkdir "!DOWNLOAD_DIR!\dispatch_solution"
if not exist "!DOWNLOAD_DIR!\reference_trading_price" mkdir "!DOWNLOAD_DIR!\reference_trading_price"

echo.
echo 下载目录: !DOWNLOAD_DIR!
echo.

:: 选择下载模式
echo 请选择下载模式:
echo   [1] 只下载 RTP 价格数据 (快速, 全量约50MB, 几分钟完成)
echo   [2] 只下载 Dispatch Solution (大文件, 全量约260GB)
echo   [3] 全部下载 (RTP + Dispatch Solution)
echo   [4] 自定义日期范围
echo   [5] 退出
echo.
set /p "MODE=请输入选项 (1-5): "

if "!MODE!"=="5" goto :end
if "!MODE!"=="4" goto :custom_range

:: 设置默认日期范围
set "START_DATE=2023-10-01"
:: 获取昨天日期
for /f %%i in ('powershell -NoProfile -Command "[datetime]::Now.AddDays(-1).ToString(\"yyyy-MM-dd\")"') do set "END_DATE=%%i"
if "!END_DATE!"=="" set "END_DATE=2026-05-18"

goto :start_download

:custom_range
echo.
set /p "START_DATE=请输入开始日期 (格式 YYYY-MM-DD, 最早 2023-10-01): "
set /p "END_DATE=请输入结束日期 (格式 YYYY-MM-DD): "
echo.
echo 请选择下载内容:
echo   [1] 只下载 RTP 价格数据
echo   [2] 只下载 Dispatch Solution
echo   [3] 全部下载
set /p "MODE=请输入选项 (1-3): "

:start_download
echo.
echo ============================================================
echo 开始下载...
echo 日期范围: !START_DATE! 至 !END_DATE!
echo ============================================================
echo.

:: 下载 FCESS 设施能力
echo [0] 下载 FCESS 设施能力表...
curl -k -s -L -o "!DOWNLOAD_DIR!\fcess_capabilities.csv" "https://data.wa.aemo.com.au/public/public-data/datafiles/fcess/fcess.csv"
if exist "!DOWNLOAD_DIR!\fcess_capabilities.csv" (
    echo     完成!
) else (
    echo     失败 (非关键, 继续...)
)
echo.

:: 根据模式选择下载内容
if "!MODE!"=="2" goto :download_dispatch
if "!MODE!"=="1" goto :download_rtp
:: MODE==3 先下载 RTP 再下载 Dispatch

:download_rtp
echo --- 下载 RTP 价格数据 ---
echo.

:: 用 PowerShell 生成日期列表到临时文件
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
echo RTP 完成: !RTP_OK! 成功, !RTP_SKIP! 跳过, !RTP_FAIL! 失败
echo.

if "!MODE!"=="1" goto :done
if "!MODE!"=="3" goto :download_dispatch
goto :done

:download_dispatch
echo --- 下载 Dispatch Solution ---
echo (每个文件约 285MB, 支持断点续传, 请耐心等待)
echo.

:: 生成日期列表
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

    :: 跳过已完成的文件 (大于 100MB 认为完整)
    set "SKIP_THIS=0"
    if exist "!FPATH!" (
        for %%f in ("!FPATH!") do (
            if %%~zf GTR 100000000 set "SKIP_THIS=1"
        )
    )

    if "!SKIP_THIS!"=="1" (
        set /a "DS_SKIP+=1"
        echo [!DS_COUNT!] !FNAME! - 已存在, 跳过
    ) else (
        echo [!DS_COUNT!] !FNAME! - 下载中...
        :: curl -C - 支持断点续传, -# 显示进度条
        curl -k -C - -L -# -o "!FPATH!" "!FURL!"
        if !errorlevel! EQU 0 (
            set /a "DS_OK+=1"
        ) else (
            echo     [警告] 下载可能不完整, 下次运行会自动续传
            set /a "DS_FAIL+=1"
        )
        :: 间隔 1 秒避免限流
        timeout /t 1 /nobreak >nul
    )
)

del "!DATE_LIST!" 2>nul
echo.
echo Dispatch Solution 完成: !DS_OK! 成功, !DS_SKIP! 跳过, !DS_FAIL! 失败
echo.

:done
echo.
echo ============================================================
echo 下载完成!
echo 数据保存在: !DOWNLOAD_DIR!
echo.
echo 目录结构:
echo   !DOWNLOAD_DIR!\dispatch_solution\     (ESS 调度解)
echo   !DOWNLOAD_DIR!\reference_trading_price\ (RTP 价格)
echo   !DOWNLOAD_DIR!\fcess_capabilities.csv   (设施能力)
echo.
echo 如需导入数据库, 运行:
echo   python scrapers/aemo_wem_ess_scraper.py --start !START_DATE! --end !END_DATE!
echo ============================================================
echo.

:end
endlocal
pause
