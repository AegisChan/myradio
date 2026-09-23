import json
import urllib.request
import urllib.parse
from datetime import datetime
import time

# 内置完整节目单 (兜底使用)
SCHEDULE_WEEKDAY = [
    {"time": "00:00", "title": "爱乐电台", "host": "阿申"},
    {"time": "00:30", "title": "金曲最动听", "host": "九头鸟"},
    {"time": "06:00", "title": "摩登旧唱片", "host": "在江湖"},
    {"time": "07:00", "title": "蓬勃早班车", "host": "燕子,晓伟"},
    {"time": "08:30", "title": "畅听经典", "host": "黄小丁"},
    {"time": "10:00", "title": "小路时间", "host": "小路"},
    {"time": "11:00", "title": "我的私房歌", "host": "在江湖"},
    {"time": "12:00", "title": "阳光正前方", "host": "吴靖"},
    {"time": "13:00", "title": "我的私房歌", "host": "在江湖"},
    {"time": "16:00", "title": "畅听经典", "host": "黄小丁"},
    {"time": "17:00", "title": "音乐好享受", "host": "贺萌"},
    {"time": "19:00", "title": "摩登旧唱片", "host": "在江湖"},
    {"time": "22:00", "title": "高光音乐时刻", "host": "在江湖"},
    {"time": "23:00", "title": "爱乐电台", "host": "阿申"}
]

SCHEDULE_WEEKEND = [
    {"time": "00:00", "title": "1038 假日经典", "host": "在江湖,贺萌等"}
]

def fetch_hbyt_schedule(date_str=None):
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')
        
    channel_name_encoded = urllib.parse.quote('湖北经典音乐广播')
    url = f"https://hbfm.hbi.tv/api/v1/channel/detail?channelName={channel_name_encoded}&startDate={date_str}&endDate={date_str}"
    
    # 自动重试机制
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            response = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
            data = json.loads(response)
            
            if data.get('success') and 'data' in data:
                segments = data['data'].get('segments', [])
                if not segments:
                    return None
                    
                schedule = []
                for seg in segments:
                    prog_id = seg.get('id', 0)
                    time_str = seg.get('startTime', '')
                    col = seg.get('column', {})
                    title = col.get('title', '未知节目')
                    
                    hosts_list = col.get('hosts', [])
                    hosts = ",".join([h.get('name', '') for h in hosts_list])
                    
                    schedule.append({"id": prog_id, "time": time_str, "title": title, "host": hosts})
                return schedule
        except Exception as e:
            print(f"尝试 {attempt + 1}/3 失败: HBYT official API scraping failed: {e}")
            time.sleep(1)
            
    return None

def get_daily_schedule(date_str=None):
    if not date_str:
        date_str = datetime.now().strftime('%Y-%m-%d')
        
    # 判断是否为周末
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    is_weekend = dt.weekday() >= 5

    scraped_schedule = fetch_hbyt_schedule(date_str)
    if scraped_schedule and len(scraped_schedule) > 0:
        return scraped_schedule
    
    if is_weekend:
        return SCHEDULE_WEEKEND
    else:
        return SCHEDULE_WEEKDAY
