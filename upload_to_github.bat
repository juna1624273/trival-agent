@echo off
echo 正在配置Git并推送到GitHub...

REM 设置Git用户信息（如果尚未设置）
git config user.name "juna1624273"
git config user.email "juna1624273@users.noreply.github.com"

REM 添加所有文件
git add .

REM 提交更改
git commit -m "Initial commit: Intelligent Travel Planning Agent System"

REM 推送到GitHub
echo 正在推送到GitHub...
git push -u origin master

if %errorlevel% neq 0 (
    echo.
    echo 推送失败！请尝试以下方法：
    echo 1. 确保您有GitHub账号并已登录
    echo 2. 在GitHub上创建名为 'trival-agent' 的仓库
    echo 3. 使用GitHub Desktop客户端上传
    echo 4. 手动通过网页上传压缩包
    echo.
    echo 压缩包位置：%cd%\..\trival-agent.tar.gz
) else (
    echo 推送成功！
)

pause