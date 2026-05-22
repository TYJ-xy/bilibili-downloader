@echo off
title B站全自动下载器
cd /d "%~dp0"

echo.
echo.  ++++++++++++++++++++++++++++++++++++++
echo.  +      B站全自动下载器  v1.4          +
echo.  ++++++++++++++++++++++++++++++++++++++
echo.

REM =========================================
REM Step 0: Find Python
REM =========================================
set PYTHON=
for %%p in (
    "%USERPROFILE%\anaconda3\python.exe"
    "%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe"
    "%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "python"
) do (
    if "%PYTHON%"=="" (
        %%p --version >nul 2>&1 && set PYTHON=%%p
    )
)

if "%PYTHON%"=="" (
    echo [错误] 未找到 Python
    echo 下载: https://www.python.org/downloads/
    pause & exit /b 1
)

echo.  Python: %PYTHON%

REM Install base dependencies
%PYTHON% -c "import httpx, tqdm" >nul 2>&1
if errorlevel 1 (
    echo.  >> 安装 httpx tqdm ...
    %PYTHON% -m pip install httpx tqdm -q
)

REM Install decord (for keyframe extraction, ~25MB one-time)
%PYTHON% -c "import decord" >nul 2>&1
if errorlevel 1 (
    echo.  >> 安装 decord - 关键帧提取用, 约25MB, 仅首次 ...
    if exist vendor\decord-*.whl (
        %PYTHON% -m pip install vendor\decord-*.whl pillow -q
    ) else (
    %PYTHON% -m pip install decord pillow -q
    )
)

REM =========================================
REM Step 1: First-run check
REM =========================================
set NEED_WIZARD=0
if exist .first_run set NEED_WIZARD=1
if %NEED_WIZARD%==0 (
    %PYTHON% check_config.py >nul 2>&1
    if errorlevel 1 set NEED_WIZARD=1
)
if %NEED_WIZARD%==1 (
    echo.
    echo.  ++++++++++++++++++++++++++++++++++++++
    echo.  +  检测到首次使用，需要配置Cookie    +
    echo.  ++++++++++++++++++++++++++++++++++++++
    echo.
    chcp 65001 >nul
    set PYTHONIOENCODING=utf-8
    %PYTHON% bilibili_auto.py config --wizard
    chcp 936 >nul
    del .first_run 2>nul
)

REM =========================================
REM Step 2: Download prompts
REM =========================================
echo.
echo.  模式: video / audio / subtitle / cover / keyframe
echo.  组合: cover,subtitle   全要: all
echo.  清晰度: 80=1080P  120=4K  64=720P(免Cookie)
echo.  关键帧: 自动用 decord 提取，无需 ffmpeg
echo.  输出: 默认到桌面
echo.  管理: python bilibili_auto.py config --wizard
echo.  (文档: SKILL.md)
echo.  -------------------------------------
echo.

set /p NAME="  UP主名称: "
if "%NAME%"=="" echo 未输入名称 & pause & exit /b

set /p MODE="  下载模式 (默认video): "
if "%MODE%"=="" set MODE=video

set /p LIMIT="  下载数量 (默认3): "
if "%LIMIT%"=="" set LIMIT=3

set /p QUALITY="  清晰度 (默认80=1080P): "
if "%QUALITY%"=="" set QUALITY=80

echo.
echo.  >> 开始: %NAME%  ^| 模式=%MODE%  ^| 数量=%LIMIT%  ^| 画质=%QUALITY%
echo.

REM =========================================
REM Step 3: Execute
REM =========================================
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
%PYTHON% bilibili_auto.py auto "%NAME%" --mode %MODE% --limit %LIMIT% --quality %QUALITY%
chcp 936 >nul

echo.
echo.  -------------------------------------
echo.  完成！文件在桌面上。
pause
