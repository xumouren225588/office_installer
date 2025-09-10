import argparse

def main(url2):
    with open("main.go","w",encoding="utf-8") as f:
        f.write(f"""
package main

import (
	"archive/zip"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"github.com/ktr0731/evans"
)

func downloadFile(url string, dest string) error {{
	// 创建进度条
	bar := evans.New()
	bar.Start()

	// 发起 HTTP 请求
	resp, err := http.Get(url)
	if err != nil {{
		return err
	}}
	defer resp.Body.Close()

	// 获取文件大小
	total := resp.ContentLength
	bar.SetTotal(int64(total))

	// 创建目标文件
	file, err := os.Create(dest)
	if err != nil {{
		return err
	}}
	defer file.Close()

	// 复制文件内容
	n, err := io.Copy(io.MultiWriter(file, bar), resp.Body)
	if err != nil {{
		return err
	}}
	bar.Incr(int64(n))
	bar.Finish()

	return nil
}}

func unzipFile(zipPath, dest string) error {{
	// 打开压缩包
	r, err := zip.OpenReader(zipPath)
	if err != nil {{
		return err
	}}
	defer r.Close()

	// 创建解压目录
	if err := os.MkdirAll(dest, 0755); err != nil {{
		return err
	}}

	// 解压文件
	for _, f := range r.File {{
		// 创建文件路径
		fpath := filepath.Join(dest, f.Name)
		if err := os.MkdirAll(filepath.Dir(fpath), 0755); err != nil {{
			return err
		}}

		// 打开文件
		rc, err := f.Open()
		if err != nil {{
			return err
		}}
		defer rc.Close()

		// 创建目标文件
		outFile, err := os.Create(fpath)
		if err != nil {{
			return err
		}}
		defer outFile.Close()

		// 复制文件内容
		_, err = io.Copy(outFile, rc)
		if err != nil {{
			return err
		}}
	}}

	return nil
}}

func main() {{
	// 指定 URL 和临时目录
	url := "{url2}"
	tempDir := filepath.Join(os.TempDir(), "mytempdir")
	zipPath := filepath.Join(tempDir, "yourfile.zip")

	// 创建临时目录
	if err := os.MkdirAll(tempDir, 0755); err != nil {{
		fmt.Printf("Error creating temp directory: %v\\n", err)
		return
	}}

	// 下载文件
	fmt.Println("Downloading file...")
	if err := downloadFile(url, zipPath); err != nil {{
		fmt.Printf("Error downloading file: %v\\n", err)
		return
	}}

	// 解压文件
	fmt.Println("Unzipping file...")
	if err := unzipFile(zipPath, tempDir); err != nil {{
		fmt.Printf("Error unzipping file: %v\\n", err)
		return
	}}

	// 删除压缩包
	if err := os.Remove(zipPath); err != nil {{
		fmt.Printf("Error removing zip file: %v\\n", err)
		return
	}}
    os.Chdir(tempDir)
	// 拼接解压目录和 setup.exe 的路径
	setupPath := filepath.Join(tempDir, "setup.exe")

	// 检查 setup.exe 是否存在
	if _, err := os.Stat(setupPath); os.IsNotExist(err) {{
		fmt.Printf("setup.exe not found in the extracted directory: %v\\n", err)
		return
	}}

	// 运行 setup.exe
	fmt.Println("Installing...")
	cmd := exec.Command(setupPath, "/configure", "config.xml")
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {{
		fmt.Printf("Error running setup.exe: %v\\n", err)
		return
	}}

	fmt.Println("Setup completed successfully!")
}}
        """)
    
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Build Office online installer')
    parser.add_argument("--url", type=str)
    args = parser.parse_args()
    url2=args.url
    main(url2)