# run_setup.py
import subprocess
import sys
from pathlib import Path

def main():
    # 获取脚本所在目录，确保相对路径正确
    base_dir = Path(__file__).parent
    setup_exe = base_dir / "tools" / "setup.exe"
    config_xml = base_dir / "config.xml"

    if not setup_exe.exists():
        sys.exit(f"[ERROR] 找不到 {setup_exe}")
    if not config_xml.exists():
        sys.exit(f"[ERROR] 找不到 {config_xml}")

    # 构造命令行
    cmd = [str(setup_exe), "/configure", str(config_xml)]

    # 启动子进程，不弹出新窗口
    # CREATE_NO_WINDOW = 0x08000000
    subprocess.run(
        cmd,
        creationflags=0x08000000,
        check=False          # 如果希望失败时抛异常，可改成 True
    )

if __name__ == "__main__":
    main()