import threading
import sys

# 检测当前是否在 Android 环境
IS_ANDROID = hasattr(sys, 'getandroidapilevel')

class AndroidNativePlayer:
    def __init__(self):
        from jnius import autoclass
        self.MediaPlayer = autoclass('android.media.MediaPlayer')
        self.player = self.MediaPlayer()
        self.is_playing_flag = False
        
    def play(self, url):
        self.stop()
        
        def _play():
            try:
                self.player.setDataSource(url)
                # prepare() 是同步阻塞的，所以在后台线程执行防止卡顿 UI
                self.player.prepare()
                self.player.start()
                self.is_playing_flag = True
            except Exception as e:
                print(f"Android MediaPlayer Error: {e}")
                
        threading.Thread(target=_play, daemon=True).start()

    def stop(self):
        try:
            if self.is_playing_flag:
                self.player.stop()
                self.is_playing_flag = False
            self.player.reset()
        except Exception as e:
            print(f"Android MediaPlayer Stop Error: {e}")
            
    def is_playing(self):
        return self.is_playing_flag

class PCPlayer:
    def __init__(self):
        self.player = None
        self.is_playing_flag = False
        
    def play(self, url):
        self.stop()
        try:
            from ffpyplayer.player import MediaPlayer
            ff_opts = {'nodisp': True, 'infbuf': True}
            self.player = MediaPlayer(url, ff_opts=ff_opts)
            self.is_playing_flag = True
        except ImportError:
            print("ffpyplayer not installed. Cannot play audio on PC.")
        
    def stop(self):
        if self.player:
            self.player.close_player()
            self.player = None
        self.is_playing_flag = False
        
    def is_playing(self):
        return self.is_playing_flag

# 工厂模式导出
def get_player():
    if IS_ANDROID:
        return AndroidNativePlayer()
    else:
        return PCPlayer()
