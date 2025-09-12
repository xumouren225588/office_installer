import argparse

def main(url2):
    with open("main.go","w",encoding="utf-8") as f:
        f.write(f"""
package main

import (
	"archive/zip"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

const (
	chunkSize = 256 * 1024 * 1024 // 256MB 每块
)

// 下载状态跟踪
type downloadState struct {{
	totalSize    int64
	downloaded   int64
	mutex        sync.Mutex
	lastPrintTime time.Time
}}

// 打印整体下载进度
func (s *downloadState) printProgress() {{
	s.mutex.Lock()
	defer s.mutex.Unlock()

	if s.totalSize <= 0 {{
		return
	}}

	// 计算百分比
	percent := float64(s.downloaded) / float64(s.totalSize) * 100

	// 进度条长度
	barLength := 50
	filledLength := int(percent / 100 * float64(barLength))
	
	// 构建进度条字符串
	bar := strings.Repeat("=", filledLength) + strings.Repeat(" ", barLength-filledLength)
	
	// 格式化显示 (MB/GB)
	var currentStr, totalStr string
	if s.totalSize < 1024*1024*1024 {{
		currentStr = fmt.Sprintf("%.1fMB", float64(s.downloaded)/1024/1024)
		totalStr = fmt.Sprintf("%.1fMB", float64(s.totalSize)/1024/1024)
	}} else {{
		currentStr = fmt.Sprintf("%.1fGB", float64(s.downloaded)/1024/1024/1024)
		totalStr = fmt.Sprintf("%.1fGB", float64(s.totalSize)/1024/1024/1024)
	}}

	// 限制打印频率，避免频繁输出
	now := time.Now()
	if now.Sub(s.lastPrintTime) > 100*time.Millisecond || s.downloaded >= s.totalSize {{
		fmt.Printf("\\rDownloading: [%-50s] %.1f%% %s/%s", bar, percent, currentStr, totalStr)
		s.lastPrintTime = now
	}}
	
	// 下载完成时换行
	if s.downloaded >= s.totalSize {{
		fmt.Println()
	}}
}}

// 下载单个块
func downloadChunk(url string, dest string, start, end int64, state *downloadState, wg *sync.WaitGroup) error {{
	defer wg.Done()
	
	// 创建块文件
	chunkFile, err := os.Create(fmt.Sprintf("%s.part%d", dest, start))
	if err != nil {{
		return err
	}}
	defer chunkFile.Close()
	
	// 创建带范围的请求
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {{
		return err
	}}
	
	// 设置范围头
	req.Header.Set("Range", fmt.Sprintf("bytes=%d-%d", start, end))
	
	// 发送请求
	client := &http.Client{{}}
	resp, err := client.Do(req)
	if err != nil {{
		return err
	}}
	defer resp.Body.Close()
	
	// 检查响应状态
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {{
		return fmt.Errorf("下载块失败: %s", resp.Status)
	}}
	
	// 读取并写入块数据
	buffer := make([]byte, 4096)
	var downloaded int64
	
	for {{
		n, err := resp.Body.Read(buffer)
		if n > 0 {{
			if _, writeErr := chunkFile.Write(buffer[:n]); writeErr != nil {{
				return writeErr
			}}
			
			downloaded += int64(n)
			
			// 更新整体进度
			state.mutex.Lock()
			state.downloaded += int64(n)
			state.mutex.Unlock()
			
			// 打印进度
			state.printProgress()
		}}
		
		if err != nil {{
			if err == io.EOF {{
				break
			}}
			return err
		}}
	}}
	
	return nil
}}

// 多线程分块下载文件
func multiThreadDownload(url string, dest string, numThreads int) error {{
	// 先发送HEAD请求获取文件大小
	resp, err := http.Head(url)
	if err != nil {{
		return err
	}}
	resp.Body.Close()
	
	// 获取文件总大小
	totalSize := resp.ContentLength
	if totalSize <= 0 {{
		return errors.New("无法获取文件大小，不支持分块下载")
	}}
	
	// 计算需要的块数
	numChunks := (totalSize + chunkSize - 1) / chunkSize
	
	// 如果块数小于线程数，调整线程数
	if numChunks < int64(numThreads) {{
		numThreads = int(numChunks)
	}}
	
	fmt.Printf("文件大小: %.2fMB，将分为 %d 块，使用 %d 线程下载\\n", 
		float64(totalSize)/1024/1024, numChunks, numThreads)
	
	// 初始化下载状态
	state := &downloadState{{
		totalSize:    totalSize,
		downloaded:   0,
		lastPrintTime: time.Now(),
	}}
	
	// 等待组，用于等待所有线程完成
	var wg sync.WaitGroup
	
	// 启动多个线程下载不同的块
	for i := 0; i < numThreads; i++ {{
		chunkIndex := int64(i)
		start := chunkIndex * chunkSize
		end := start + chunkSize - 1
		
		// 最后一块可能小于chunkSize
		if end >= totalSize {{
			end = totalSize - 1
		}}
		
		// 如果已经超出范围，退出循环
		if start >= totalSize {{
			break
		}}
		
		wg.Add(1)
		go downloadChunk(url, dest, start, end, state, &wg)
		
		// 简单的延迟避免同时发起太多连接
		time.Sleep(100 * time.Millisecond)
	}}
	
	// 等待所有块下载完成
	wg.Wait()
	
	// 验证所有块都已下载
	if state.downloaded != totalSize {{
		return fmt.Errorf("下载不完整，已下载 %d 字节，总大小 %d 字节", 
			state.downloaded, totalSize)
	}}
	
	// 合并所有块
	outputFile, err := os.Create(dest)
	if err != nil {{
		return err
	}}
	defer outputFile.Close()
	
	// 合并每个块
	for i := int64(0); i < numChunks; i++ {{
		start := i * chunkSize
		chunkFileName := fmt.Sprintf("%s.part%d", dest, start)
		
		// 打开块文件
		chunkFile, err := os.Open(chunkFileName)
		if err != nil {{
			return err
		}}
		
		// 复制到输出文件
		if _, err := io.Copy(outputFile, chunkFile); err != nil {{
			chunkFile.Close()
			return err
		}}
		
		// 关闭并删除块文件
		chunkFile.Close()
		os.Remove(chunkFileName)
	}}
	
	return nil
}}

// 解压文件（保持不变）
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
	// 指定 URL 和临时目录
	url := "{url2}"
	tempDir := filepath.Join(os.TempDir(), "mytempdir")
	zipPath := filepath.Join(tempDir, "yourfile.zip")

	// 创建临时目录
	if err := os.MkdirAll(tempDir, 0755); err != nil {{
		fmt.Printf("创建临时目录失败: %v\\n", err)
		return
	}}

	// 下载文件（使用4个线程）
	fmt.Println("开始下载文件...")
	if err := multiThreadDownload(url, zipPath, 4); err != nil {{
		fmt.Printf("下载文件失败: %v\\n", err)
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
	cmd := exec.Command(setupPath, "/configure", "config.xml")
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
