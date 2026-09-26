import threading
import sys

# 检测当前是否在 Android 环境
IS_ANDROID = hasattr(sys, 'getandroidapilevel')

class AndroidNativePlayer:
    def __init__(self):
        self.player = None
        self.is_playing_flag = False
        self.duration = 0
        
    def play(self, url):
        self.stop()
        
        def _play():
            try:
                from jnius import autoclass
                Looper = autoclass('android.os.Looper')
                if not Looper.myLooper():
                    Looper.prepare()
                
                self.player = autoclass('android.media.MediaPlayer')()
                self.player.setDataSource(url)
                self.player.prepare()
                self.player.start()
                self.is_playing_flag = True
                self.duration = self.player.getDuration()
            except Exception as e:
                print(f"Android MediaPlayer Error: {e}")
                
        threading.Thread(target=_play, daemon=True).start()

    def stop(self):
        try:
            if self.is_playing_flag and self.player:
                self.player.stop()
                self.is_playing_flag = False
            if self.player:
                self.player.reset()
                self.player.release()
                self.player = None
                self.duration = 0
        except Exception as e:
            print(f"Android MediaPlayer Stop Error: {e}")
            
    def is_playing(self):
        return self.is_playing_flag
        
    def get_position(self):
        try:
            if self.is_playing_flag and self.player:
                return self.player.getCurrentPosition()
        except:
            pass
        return 0
        
    def get_duration(self):
        try:
            if self.is_playing_flag and self.player:
                return self.player.getDuration()
        except:
            pass
        return self.duration
        
    def seek(self, position_ms):
        try:
            if self.is_playing_flag and self.player:
                self.player.seekTo(int(position_ms))
        except:
            pass

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
        
    def get_position(self):
        return 0
        
    def get_duration(self):
        return 0
        
    def seek(self, position_ms):
        pass

# 工厂模式导出
def get_player():
    if IS_ANDROID:
        return AndroidNativePlayer()
    else:
        return PCPlayer()
