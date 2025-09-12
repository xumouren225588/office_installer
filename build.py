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
	chunkSize  = 256 * 1024 * 1024 // 256MB 每块
	maxRetries = 3                 // 最大重试次数
	retryDelay = 5 * time.Second   // 重试延迟
)

// 下载状态跟踪
type downloadState struct {{
	totalSize      int64
	downloaded     int64
	mutex          sync.Mutex
	lastPrintTime  time.Time
	completedChunks map[int64]bool // 已完成的块索引
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

// 下载单个块（带重试机制）
func downloadChunk(url string, dest string, start, end int64, state *downloadState, wg *sync.WaitGroup) error {{
	defer wg.Done()
	
	// 检查该块是否已完成
	state.mutex.Lock()
	if state.completedChunks[start] {{
		state.mutex.Unlock()
		return nil
	}}
	state.mutex.Unlock()
	
	chunkFileName := fmt.Sprintf("%s.part%d", dest, start)
	
	// 检查是否有部分下载的块
	var resumeStart int64 = start
	if fi, err := os.Stat(chunkFileName); err == nil {{
		// 如果文件存在且大小大于0，尝试续传
		if fi.Size() > 0 {{
			resumeStart = start + fi.Size()
			// 如果已经下载完成，标记为已完成并返回
			if resumeStart > end {{
				state.mutex.Lock()
				state.completedChunks[start] = true
				state.downloaded += (end - start + 1)
				state.mutex.Unlock()
				return nil
			}}
			fmt.Printf("继续下载块 %d (从 %d 到 %d)\\n", start/chunkSize+1, resumeStart, end)
		}}
	}}
	
	// 创建块文件（追加模式）
	flags := os.O_WRONLY | os.O_CREATE
	if resumeStart > start {{
		flags |= os.O_APPEND
	}} else {{
		flags |= os.O_TRUNC
	}}
	
	chunkFile, err := os.OpenFile(chunkFileName, flags, 0644)
	if err != nil {{
		return err
	}}
	defer chunkFile.Close()
	
	// 重试机制
	for retry := 0; retry < maxRetries; retry++ {{
		if retry > 0 {{
			fmt.Printf("重试下载块 %d (第 %d 次重试)\\n", start/chunkSize+1, retry)
			time.Sleep(retryDelay)
		}}
		
		// 创建带范围的请求
		req, err := http.NewRequest("GET", url, nil)
		if err != nil {{
			return err
		}}
		
		// 设置范围头
		req.Header.Set("Range", fmt.Sprintf("bytes=%d-%d", resumeStart, end))
		
		// 发送请求
		client := &http.Client{{
			Timeout: 5 * time.Minute, // 设置超时时间
		}}
		resp, err := client.Do(req)
		if err != nil {{
			fmt.Printf("块 %d 下载失败: %v\\n", start/chunkSize+1, err)
			continue
		}}
		
		// 检查响应状态
		if resp.StatusCode < 200 || resp.StatusCode >= 300 {{
			resp.Body.Close()
			fmt.Printf("块 %d 下载失败: %s\\n", start/chunkSize+1, resp.Status)
			continue
		}}
		
		// 读取并写入块数据
		buffer := make([]byte, 4096)
		var chunkDownloaded int64
		
		for {{
			n, err := resp.Body.Read(buffer)
			if n > 0 {{
				if _, writeErr := chunkFile.Write(buffer[:n]); writeErr != nil {{
					resp.Body.Close()
					return writeErr
				}}
				
				chunkDownloaded += int64(n)
				
				// 更新整体进度
				state.mutex.Lock()
				state.downloaded += int64(n)
				state.mutex.Unlock()
				
				// 打印进度
				state.printProgress()
			}}
			
			if err != nil {{
				resp.Body.Close()
				if err == io.EOF {{
					// 块下载完成
					state.mutex.Lock()
					state.completedChunks[start] = true
					state.mutex.Unlock()
					return nil
				}}
				fmt.Printf("块 %d 读取失败: %v\\n", start/chunkSize+1, err)
				break
			}}
		}}
	}}
	
	return fmt.Errorf("块 %d 达到最大重试次数", start/chunkSize+1)
}}

// 多线程分块下载文件（每个块一个线程）
func multiThreadDownload(url string, dest string) error {{
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
	fmt.Printf("文件大小: %.2fMB，将分为 %d 块，每块一个线程\\n", 
		float64(totalSize)/1024/1024, numChunks)
	
	// 初始化下载状态
	state := &downloadState{{
		totalSize:      totalSize,
		downloaded:     0,
		lastPrintTime:  time.Now(),
		completedChunks: make(map[int64]bool),
	}}
	
	// 检查已下载的块并计算已下载大小
	for i := int64(0); i < numChunks; i++ {{
		start := i * chunkSize
		end := start + chunkSize - 1
		if end >= totalSize {{
			end = totalSize - 1
		}}
		
		chunkFileName := fmt.Sprintf("%s.part%d", dest, start)
		if fi, err := os.Stat(chunkFileName); err == nil {{
			// 检查文件大小是否匹配块大小
			if fi.Size() == end - start + 1 {{
				state.completedChunks[start] = true
				state.downloaded += fi.Size()
			}}
		}}
	}}
	
	// 如果已经全部下载完成，直接返回
	if state.downloaded == totalSize {{
		fmt.Println("文件已完全下载，无需重复下载")
		return nil
	}}
	
	// 显示已下载进度
	if state.downloaded > 0 {{
		fmt.Printf("发现部分下载，已完成 %.1f%%\\n", 
			float64(state.downloaded)/float64(totalSize)*100)
	}}
	
	// 等待组，用于等待所有线程完成
	var wg sync.WaitGroup
	
	// 为每个块启动一个线程
	for i := int64(0); i < numChunks; i++ {{
		start := i * chunkSize
		end := start + chunkSize - 1
		
		// 最后一块可能小于chunkSize
		if end >= totalSize {{
			end = totalSize - 1
		}}
		
		// 如果已经完成，跳过
		state.mutex.Lock()
		if state.completedChunks[start] {{
			state.mutex.Unlock()
			continue
		}}
		state.mutex.Unlock()
		
		wg.Add(1)
		go downloadChunk(url, dest, start, end, state, &wg)
		
		// 添加延迟避免瞬间创建过多连接
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

// 解压文件
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

	// 下载文件（每个块一个线程）
	fmt.Println("开始下载文件...")
	if err := multiThreadDownload(url, zipPath); err != nil {{
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
