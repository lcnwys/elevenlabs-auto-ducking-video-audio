#!/usr/bin/env bash
set -euo pipefail
printf '阿里云 CLI 检查（只读，不部署或修改云资源）\n'
if ! command -v aliyun >/dev/null 2>&1; then
  printf '未安装 aliyun。macOS 可使用：brew install aliyun-cli\n'
  exit 2
fi
aliyun version
printf '\n可选：查看已存在的凭证配置（不打印密钥）：\n'
aliyun configure list
printf '\n验证 OAuth/RAM 身份，按需运行：\n'
printf 'aliyun sts get-caller-identity --profile fc-ducking-dev\n'
