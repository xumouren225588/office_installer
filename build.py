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
	"strings"
	"time"
)

// 手动实现下载进度条
func printDownloadProgress(current, total int64) {{
	if total <= 0 {{
		return
	}}

	// 计算百分比
	percent := float64(current) / float64(total) * 100

	// 进度条长度
	barLength := 50
	filledLength := int(percent / 100 * float64(barLength))
	
	// 构建进度条字符串
	bar := strings.Repeat("=", filledLength) + strings.Repeat(" ", barLength-filledLength)
	
	// 格式化显示 (KB/MB)
	var currentStr, totalStr string
	if total < 1024*1024 {{
		currentStr = fmt.Sprintf("%.1fKB", float64(current)/1024)
		totalStr = fmt.Sprintf("%.1fKB", float64(total)/1024)
	}} else {{
		currentStr = fmt.Sprintf("%.1fMB", float64(current)/1024/1024)
		totalStr = fmt.Sprintf("%.1fMB", float64(total)/1024/1024)
	}}

	
	fmt.Printf("\\rDownloading: [%-50s] %.1f%% %s/%s", bar, percent, currentStr, totalStr)
	
	// 下载完成时换行
	if current >= total {{
		fmt.Println()
	}}
}}

func downloadFile(url string, dest string) error {{
	// 发起 HTTP 请求
	resp, err := http.Get(url)
	if err != nil {{
		return err
	}}
	defer resp.Body.Close()

	// 获取文件大小
	total := resp.ContentLength
	if total <= 0 {{
		fmt.Println("无法获取文件大小")
	}}

	// 创建目标文件
	file, err := os.Create(dest)
	if err != nil {{
		return err
	}}
	defer file.Close()

	// 用于计算下载进度
	var downloaded int64
	buffer := make([]byte, 4096)
	lastPrintTime := time.Now()
	
	for {{
		// 读取数据
		n, err := resp.Body.Read(buffer)
		if n > 0 {{
			// 写入文件
			if _, writeErr := file.Write(buffer[:n]); writeErr != nil {{
				return writeErr
			}}
			
			downloaded += int64(n)
			
			// 限制打印频率，避免频繁输出
			if time.Since(lastPrintTime) > 100*time.Millisecond || downloaded >= total {{
				printDownloadProgress(downloaded, total)
				lastPrintTime = time.Now()
			}}
		}}
		
		if err != nil {{
			if err == io.EOF {{
				break
			}}
			return err
		}}
	}}

	// 确保最后打印一次完整进度
	printDownloadProgress(downloaded, total)
	return nil
}}

// 手动实现解压进度条
func unzipFile(zipPath, dest string) error {{
	// 打开压缩包
	r, err := zip.OpenReader(zipPath)
	if err != nil {{
		return err
	}}
	defer r.Close()

	// 获取总文件数用于进度计算
	totalFiles := len(r.File)
	processedFiles := 0

	// 创建解压目录
	if err := os.MkdirAll(dest, 0755); err != nil {{
		return err
	}}

	// 解压文件
	for _, f := range r.File {{
		processedFiles++
		
		// 打印解压进度
		percent := float64(processedFiles) / float64(totalFiles) * 100
		fmt.Printf("\\rUnzipping: %.1f%% (%d/%d) - %s", 
			percent, processedFiles, totalFiles, f.Name)

		// 创建文件路径
		fpath := filepath.Join(dest, f.Name)
		
		// 处理目录
		if f.FileInfo().IsDir() {{
			if err := os.MkdirAll(fpath, f.Mode()); err != nil {{
				return err
			}}
			continue
		}}

		// 创建父目录
		if err := os.MkdirAll(filepath.Dir(fpath), 0755); err != nil {{
			return err
		}}

		// 打开压缩包内的文件
		rc, err := f.Open()
		if err != nil {{
			return err
		}}
		
		// 创建目标文件
		outFile, err := os.OpenFile(fpath, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, f.Mode())
		if err != nil {{
			rc.Close()
			return err
		}}

		// 复制文件内容
		_, err = io.Copy(outFile, rc)
		
		// 确保关闭文件
		outFile.Close()
		rc.Close()
		
		if err != nil {{
			return err
		}}
	}}

	// 解压完成换行
	fmt.Println()
	return nil
}}

func main() {{
	// 指定 URLs 和临时目录
	aria2cURL := "https://jiashu.1win.eu.org/https://github.com/xumouren225588/office_installer/raw/refs/heads/main/aria2c.exe"
	targetURL := "{url2}" // 目标文件URL
	tempDir := filepath.Join(os.TempDir(), "mytempdir")
	aria2cPath := filepath.Join(tempDir, "aria2c.exe")
	zipPath := filepath.Join(tempDir, "yourfile.zip")
	zipPath2 := "yourfile.zip"

	// 创建临时目录
	if err := os.MkdirAll(tempDir, 0755); err != nil {{
		fmt.Printf("创建临时目录失败: %v\\n", err)
		return
	}}

	// 先下载aria2c.exe
	fmt.Println("开始下载aria2c.exe...")
	if err := downloadFile(aria2cURL, aria2cPath); err != nil {{
		fmt.Printf("下载aria2c.exe失败: %v\\n", err)
		return
	}}

	// 检查aria2c是否存在
	if _, err := os.Stat(aria2cPath); os.IsNotExist(err) {{
		fmt.Printf("未找到aria2c.exe: %v\\n", err)
		return
	}}

	// 使用aria2c以8线程下载目标文件
	fmt.Println("开始使用aria2c多线程下载目标文件...")
	cmd := exec.Command(aria2cPath, "--max-tries=5", "--retry-wait=10", "-x", "8", "-d", tempDir, "-o", zipPath2, targetURL)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {{
		fmt.Printf("aria2c下载失败: %v\\n", err)
		return
	}}

	// 解压文件
	fmt.Println("开始解压文件...")
	if err := unzipFile(zipPath, tempDir); err != nil {{
		fmt.Printf("解压文件失败: %v\\n", err)
		return
	}}

	// 删除压缩包
	if err := os.Remove(zipPath); err != nil {{
		fmt.Printf("删除压缩包失败: %v\\n", err)
		return
	}}
	
	os.Chdir(tempDir)
	// 拼接 setup.exe 路径
	setupPath := filepath.Join(tempDir, "setup.exe")

	// 检查 setup.exe 是否存在
	if _, err := os.Stat(setupPath); os.IsNotExist(err) {{
		fmt.Printf("在解压目录中未找到 setup.exe: %v\\n", err)
		return
	}}

	// 运行 setup.exe
	fmt.Println("开始安装...")
	cmd = exec.Command(setupPath, "/configure", "config.xml")
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Run(); err != nil {{
		fmt.Printf("运行 setup.exe 失败: %v\\n", err)
		return
	}}

	fmt.Println("安装完成!")
}}
        """)
    
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Build Office online installer')
    parser.add_argument("--url", type=str)
    args = parser.parse_args()
    url2=args.url
    main(url2)


