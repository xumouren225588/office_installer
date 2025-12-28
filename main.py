# run_setup.py
import subprocess

def main():
    # 构造命令行
    cmd = [".\\tools\\setup.exe", "/configure", "config.xml"]

    subprocess.run(
        cmd,
        creationflags=0x08000000,
        check=True          # 如果希望失败时抛异常，可改成 True
    )

if __name__ == "__main__":
    main()

