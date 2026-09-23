import threading
import time
import urllib.request
import os

class HLSRecorder:
    def __init__(self, m3u8_url, output_path):
        self.m3u8_url = m3u8_url
        self.output_path = output_path
        self.is_recording = False
        self.downloaded_chunks = set()
        
    def start(self):
        self.is_recording = True
        threading.Thread(target=self._record_loop, daemon=True).start()
        
    def stop(self):
        self.is_recording = False
        
    def _fetch_playlist(self, url):
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        return urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
        
    def _record_loop(self):
        # 针对 hbfm.hbi.tv 的变体 m3u8 逻辑
        base_url = "https://fs.hbfm.hbi.tv"
        try:
            # 1. 尝试获取主 m3u8
            main_m3u8 = self._fetch_playlist(self.m3u8_url)
            # 解析出子 m3u8
            sub_url = None
            for line in main_m3u8.split('\n'):
                if line.startswith('/live/') or line.startswith('http'):
                    sub_url = line.strip()
                    if not sub_url.startswith('http'):
                        sub_url = base_url + sub_url
                    break
            
            if not sub_url:
                sub_url = self.m3u8_url
                
            # 2. 循环抓取子 m3u8 中的 ts 分片
            with open(self.output_path, 'wb') as outfile:
                while self.is_recording:
                    try:
                        sub_m3u8 = self._fetch_playlist(sub_url)
                        lines = sub_m3u8.split('\n')
                        for line in lines:
                            if line.endswith('.ts') or '.ts?' in line:
                                chunk_name = line.strip()
                                if chunk_name not in self.downloaded_chunks:
                                    # 构造 ts 完整下载链接
                                    chunk_url = chunk_name if chunk_name.startswith('http') else base_url + '/live/' + chunk_name
                                    
                                    # 下载并写入文件
                                    req = urllib.request.Request(chunk_url, headers={'User-Agent': 'Mozilla/5.0'})
                                    ts_data = urllib.request.urlopen(req, timeout=10).read()
                                    outfile.write(ts_data)
                                    
                                    self.downloaded_chunks.add(chunk_name)
                                    print(f"Downloaded chunk: {chunk_name}")
                    except Exception as loop_e:
                        print(f"HLS Chunk fetch error: {loop_e}")
                    
                    # 休息 5 秒钟再次拉取新的 m3u8 列表
                    time.sleep(5)
        except Exception as e:
            print(f"HLS Recording stopped due to error: {e}")
            self.is_recording = False
