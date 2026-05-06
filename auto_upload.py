#!/usr/bin/env python3
"""
自动上传项目到GitHub的脚本
只需要运行一次，输入GitHub用户名和Personal Access Token即可
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, check=True):
    """运行shell命令"""
    print(f"执行: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"错误: {result.stderr}")
        if check:
            sys.exit(1)
    else:
        if result.stdout:
            print(result.stdout)
    return result

def main():
    print("=== 自动上传到GitHub工具 ===\n")

    # 检查是否在git仓库中
    if not Path(".git").exists():
        print("初始化Git仓库...")
        run_command("git init")

    # 配置用户信息
    print("配置Git用户信息...")
    run_command("git config user.name \"juna1624273\"")
    run_command("git config user.email \"juna1624273@users.noreply.github.com\"")

    # 添加所有文件
    print("添加文件到Git...")
    run_command("git add .", check=False)

    # 提交更改
    print("提交更改...")
    run_command("git commit -m \"Initial commit: Intelligent Travel Planning Agent System\"", check=False)

    # 设置远程仓库
    print("设置远程仓库...")
    run_command("git remote remove origin", check=False)
    run_command("git remote add origin https://github.com/juna1624273/trival-agent.git")

    # 获取GitHub凭据
    print("\n需要您的GitHub凭据来推送代码...")
    print("请访问 https://github.com/settings/tokens 创建Personal Access Token")
    print("需要的权限: repo (全部勾选)\n")

    username = input("GitHub用户名: ").strip()
    if not username:
        username = "juna1624273"

    token = input("Personal Access Token: ").strip()

    if not token:
        print("错误: 必须提供Personal Access Token")
        sys.exit(1)

    # 更新远程URL包含凭据
    auth_url = f"https://{username}:{token}@github.com/juna1624273/trival-agent.git"
    run_command(f"git remote set-url origin {auth_url}")

    # 推送到GitHub
    print("\n正在推送到GitHub...")
    result = run_command("git push -u origin master", check=False)

    if result.returncode == 0:
        print("\n✅ 上传成功！")
        print("您的项目已上传到: https://github.com/juna1624273/trival-agent")
    else:
        print("\n❌ 上传失败，正在尝试备用方案...")

        # 尝试创建并推送main分支
        print("尝试创建main分支...")
        run_command("git branch -M main", check=False)
        result = run_command("git push -u origin main", check=False)

        if result.returncode == 0:
            print("\n✅ 上传成功（使用main分支）！")
            print("您的项目已上传到: https://github.com/juna1624273/trival-agent")
        else:
            print("\n❌ 仍然失败，请检查：")
            print("1. Personal Access Token是否正确")
            print("2. 网络连接是否正常")
            print("3. 仓库是否已存在")
            print("\n备用方案：手动上传压缩包")
            print("压缩包位置:", Path("../trival-agent.tar.gz").absolute())

if __name__ == "__main__":
    main()