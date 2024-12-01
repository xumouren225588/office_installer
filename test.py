from ed2k_link_parser import parse_ed2k_link, download_ed2k_link

# 解析ed2k链接
link = "ed2k://|file|example_file.txt|12345|ABCDEF1234567890|/"
metadata = parse_ed2k_link(link)

# 打印文件信息
print("文件名:", metadata.filename)
print("文件大小:", metadata.filesize)

# 下载文件
download_ed2k_link(link, save_as="example_file.txt")
