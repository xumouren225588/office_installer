from ed2k_link_parser import parse_ed2k_link, download_ed2k_link

# 解析ed2k链接
link = "ed2k://|file|cn_windows_10_business_editions_version_1909_updated_jan_2020_x64_dvd_b3e1f3a6.iso|5311711232|3527D2A9845FF4105F485CC364655B66|/"
metadata = parse_ed2k_link(link)

# 打印文件信息
print("文件名:", metadata.filename)
print("文件大小:", metadata.filesize)

# 下载文件

