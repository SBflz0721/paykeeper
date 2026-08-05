"""pytest 共享配置：把仓库根目录加入 sys.path（tests/ 独立于 agent 包运行）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 测试统一使用的合法地址（任意格式正确的 EOA 地址即可）
VALID_ADDR = "0xc4Ef9855219C03843dd425b23C142d0F059aAfFd"
