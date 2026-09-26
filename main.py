import traceback

try:
    from kivy.core.text import LabelBase
    # 全局注册中文字体为微软雅黑 (msyh.ttc)
    LabelBase.register(name="CustomFont", fn_regular="msyh.ttc")
    
    from kivymd.app import MDApp
    from kivymd.uix.screen import MDScreen
    from kivymd.uix.boxlayout import MDBoxLayout
    from kivymd.uix.gridlayout import MDGridLayout
    from kivymd.uix.toolbar import MDTopAppBar
    from kivymd.uix.menu import MDDropdownMenu
    from kivymd.uix.label import MDLabel
    from kivymd.uix.card import MDCard
    from kivymd.uix.fitimage import FitImage
    from kivy.uix.scrollview import ScrollView
    from kivy.clock import Clock
    from kivy.clock import mainthread
    from kivy.core.window import Window
    from kivy.utils import get_color_from_hex
    
    from datetime import datetime, timedelta
    import threading
    import os
    import urllib.request
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context
    
    from radio_api import get_daily_schedule
    from android_player import get_player
    from hls_recorder import HLSRecorder
    
    # 纯净极简的文字居中自适应按键
    class CustomRectBtn(MDCard):
        def __init__(self, text, bg_color, on_click, **kwargs):
            super().__init__(**kwargs)
            self.size_hint_y = None
            self.height = "42dp"
            self.size_hint_x = 1 # 等分拉伸
            self.md_bg_color = bg_color
            self.radius = [8, 8, 8, 8] # 矩形+小圆倒角
            self.ripple_behavior = True
            self.elevation = 0
            
            self.bind(on_release=on_click)
            
            self.label_widget = MDLabel(
                text=text, 
                theme_text_color="Custom", 
                text_color=(1,1,1,0.9), 
                halign="center", 
                valign="center",
                font_style="Body1"
            )
            self.add_widget(self.label_widget)
            
        def update_state(self, text, active=False):
            self.label_widget.text = text
            if active:
                self.md_bg_color = (1, 1, 1, 0.35) # 激活时变亮
                self.label_widget.text_color = get_color_from_hex("#60A5FA") # 亮蓝色
            else:
                self.md_bg_color = (1, 1, 1, 0.15) # 恢复原本半透明
                self.label_widget.text_color = (1, 1, 1, 0.9)

    # 自定义紧凑且偏左的节目列表项
    class ProgramListItem(MDCard):
        def __init__(self, prog, app_instance, **kwargs):
            super().__init__(**kwargs)
            self.prog = prog
            self.app = app_instance
            self.size_hint_y = None
            self.height = "54dp" # 减少间距，更加紧凑
            self.md_bg_color = (0, 0, 0, 0)
            self.elevation = 0
            self.ripple_behavior = True
            self.padding = ["20dp", "8dp", "20dp", "8dp"] # 整体偏左对齐
            self.bind(on_release=self.on_click)
            
            self.layout = MDBoxLayout(orientation="vertical", spacing="2dp")
            self.title_label = MDLabel(
                text=f"{prog['time']} - {prog['title']}", 
                font_style="Body1", 
                theme_text_color="Custom", 
                text_color=(1, 1, 1, 0.95),
                halign="left"
            )
            self.subtitle_label = MDLabel(
                text=f"主播: {prog['host']}", 
                font_style="Caption", 
                theme_text_color="Custom", 
                text_color=(1, 1, 1, 0.6),
                halign="left"
            )
            self.layout.add_widget(self.title_label)
            self.layout.add_widget(self.subtitle_label)
            self.add_widget(self.layout)
            
        def on_click(self, *args):
            self.app.on_program_select(self.prog, self)

    class RadioApp(MDApp):
        def build(self):
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.INTERNET, Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])
            except Exception:
                pass

            self.theme_cls.material_style = "M3"
            self.theme_cls.theme_style = "Dark"
            
            # 全局缩放字体，使用微软雅黑
            for style in self.theme_cls.font_styles.keys():
                if style != "Icons":
                    self.theme_cls.font_styles[style][0] = "CustomFont"
                    orig_size = self.theme_cls.font_styles[style][1]
                    self.theme_cls.font_styles[style][1] = int(orig_size * 0.9)
            
            self.player = get_player()
            self.live_recorder = None
            self.current_date = datetime.now().strftime('%Y-%m-%d')
            self.schedule_data = []
            self.selected_program = None
            self.list_item_widgets = []
            
            self.screen = MDScreen()
            
            # 背景图
            bg_image = FitImage(source="background.png")
            self.screen.add_widget(bg_image)
            
            # 遮罩: 大幅提升透明度 (0.65 -> 0.25)，让背景图更亮更通透
            overlay = MDBoxLayout(md_bg_color=(0.0, 0.0, 0.05, 0.25), orientation='vertical')
            self.screen.add_widget(overlay)
            
            # 导航栏
            self.toolbar = MDTopAppBar(
                title="湖北经典音乐广播 (今天)",
                elevation=0,
                md_bg_color=(0, 0, 0, 0.15),
                specific_text_color=(1, 1, 1, 1),
                right_action_items=[["calendar", lambda x: self.open_date_menu(x)]]
            )
            overlay.add_widget(self.toolbar)
            
            # 列表 (紧凑型布局)
            scroll = ScrollView()
            self.list_layout = MDBoxLayout(orientation="vertical", adaptive_height=True, spacing="2dp", padding=["0dp", "10dp", "0dp", "10dp"])
            scroll.add_widget(self.list_layout)
            overlay.add_widget(scroll)
            
            # 底部控制台
            bottom_container = MDBoxLayout(
                size_hint_y=None, 
                padding=["15dp", "10dp", "15dp", "25dp"],
                md_bg_color=(0, 0, 0, 0.4), # 控制台区域稍暗，增强按键对比
                orientation="vertical",
                spacing="15dp"
            )
            bottom_container.bind(minimum_height=bottom_container.setter('height'))
            
            # 状态文本
            self.status_label = MDLabel(
                text="准备就绪，请选择节目", 
                halign="center", 
                valign="center",
                theme_text_color="Custom",
                text_color=(1, 1, 1, 0.8),
                size_hint_y=None,
                height="24dp",
                font_style="Body2"
            )
            bottom_container.add_widget(self.status_label)
            
            # 4个均匀分布的按键 (2x2 网格)
            btn_grid = MDGridLayout(cols=2, spacing="15dp", size_hint_y=None)
            btn_grid.bind(minimum_height=btn_grid.setter('height'))
            
            # 同一色系（玻璃质感的高级白灰半透明）
            glass_color = (1, 1, 1, 0.15)
            
            self.play_btn = CustomRectBtn("播放回放", glass_color, self.toggle_play)
            self.download_btn = CustomRectBtn("下载回放", glass_color, self.download_replay)
            self.live_btn = CustomRectBtn("播放直播", glass_color, self.play_live)
            self.record_btn = CustomRectBtn("录制直播", glass_color, self.record_live)
            
            btn_grid.add_widget(self.play_btn)
            btn_grid.add_widget(self.download_btn)
            btn_grid.add_widget(self.live_btn)
            btn_grid.add_widget(self.record_btn)
            
            bottom_container.add_widget(btn_grid)
            overlay.add_widget(bottom_container)
            
            self.init_date_menu()
            Clock.schedule_once(lambda dt: self.load_schedule(self.current_date), 0.5)
            
            return self.screen

        def set_keep_screen_on(self, keep_on):
            try:
                from jnius import autoclass
                from android.runnable import run_on_ui_thread
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                WindowManager = autoclass('android.view.WindowManager$LayoutParams')
                context = PythonActivity.mActivity
                @run_on_ui_thread
                def _keep_on():
                    if keep_on:
                        context.getWindow().addFlags(WindowManager.FLAG_KEEP_SCREEN_ON)
                    else:
                        context.getWindow().clearFlags(WindowManager.FLAG_KEEP_SCREEN_ON)
                _keep_on()
            except Exception:
                pass

        def init_date_menu(self):
            menu_items = []
            weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            for i in range(30):
                d = datetime.now() - timedelta(days=i)
                label = f"{d.strftime('%Y-%m-%d')} ({weekdays[d.weekday()]})"
                if i == 0: label = f"{d.strftime('%Y-%m-%d')} (今天)"
                if i == 1: label = f"{d.strftime('%Y-%m-%d')} (昨天)"
                
                menu_items.append({
                    "text": label,
                    "viewclass": "OneLineListItem",
                    "on_release": lambda x=d.strftime('%Y-%m-%d'), y=label: self.on_date_select(x, y),
                })
                
            self.menu = MDDropdownMenu(
                items=menu_items,
                width_mult=4,
                background_color=(0.15, 0.15, 0.15, 0.95)
            )

        def open_date_menu(self, button):
            self.menu.caller = button
            self.menu.open()

        def on_date_select(self, date_str, label):
            self.menu.dismiss()
            self.current_date = date_str
            date_label = label.split()[1] if " " in label else label
            self.toolbar.title = f"湖北经典音乐广播 {date_label}"
            self.load_schedule(date_str)

        def load_schedule(self, date_str):
            self.status_label.text = "正在获取节目单..."
            
            def _fetch():
                data = get_daily_schedule(date_str)
                self.update_ui_schedule(data)
                
            threading.Thread(target=_fetch, daemon=True).start()

        @mainthread
        def update_ui_schedule(self, data):
            self.schedule_data = data
            self.list_layout.clear_widgets()
            self.list_item_widgets.clear()
            
            if not data:
                self.status_label.text = "获取失败"
                return
                
            for prog in data:
                item = ProgramListItem(prog=prog, app_instance=self)
                self.list_item_widgets.append(item)
                self.list_layout.add_widget(item)
                
            self.status_label.text = "节目单加载完成"

        def on_program_select(self, prog, clicked_item):
            self.selected_program = prog
            self.status_label.text = f"已选中: {prog['title']}"
            
            for item in self.list_item_widgets:
                if item == clicked_item:
                    item.md_bg_color = (1, 1, 1, 0.25) # 选中背景变亮
                    item.title_label.text = f"▶ {item.prog['time']} - {item.prog['title']}"
                    item.title_label.text_color = get_color_from_hex("#60A5FA")
                    item.subtitle_label.text_color = get_color_from_hex("#93C5FD")
                else:
                    item.md_bg_color = (0, 0, 0, 0)
                    item.title_label.text = f"{item.prog['time']} - {item.prog['title']}"
                    item.title_label.text_color = (1, 1, 1, 0.95)
                    item.subtitle_label.text_color = (1, 1, 1, 0.6)

        def stop_all(self):
            if self.player.is_playing():
                self.player.stop()
            self.play_btn.update_state("播放回放", active=False)
            self.live_btn.update_state("播放直播", active=False)
            self.set_keep_screen_on(False)

        def play_live(self, instance):
            if self.player.is_playing() and self.live_btn.label_widget.text == "停止直播":
                self.stop_all()
                self.status_label.text = "已停止直播"
                return
                
            self.stop_all()
            self.status_label.text = "正在连接直播源..."
            self.player.play("https://fs.hbfm.hbi.tv/live/jdyy.m3u8")
            self.live_btn.update_state("停止直播", active=True)
            self.set_keep_screen_on(True)

        def toggle_play(self, instance):
            if self.player.is_playing() and self.play_btn.label_widget.text == "停止回放":
                self.stop_all()
                self.status_label.text = "已停止回放"
                return
                
            if not self.selected_program:
                self.status_label.text = "请先在列表中选择一个节目！"
                return
                
            if self.current_date != datetime.now().strftime('%Y-%m-%d') and not self.selected_program.get('id'):
                self.status_label.text = "离线固化数据无回放链接！"
                return
                
            prog_id = self.selected_program.get('id')
            if prog_id:
                self.stop_all()
                yyyymm = self.current_date.replace("-", "")[:6]
                replay_url = f"https://fs.hbfm.hbi.tv/recorder/jdyy/{yyyymm}/{prog_id}.mp3"
                self.status_label.text = f"正在缓冲回放: {self.selected_program['title']}..."
                self.player.play(replay_url)
                self.play_btn.update_state("停止回放", active=True)
                self.set_keep_screen_on(True)
            else:
                self.status_label.text = "当前节目无回放资源，请点击'播放直播'"

        def get_save_dir(self):
            try:
                from android.storage import primary_external_storage_path
                save_dir = os.path.join(primary_external_storage_path(), "Download", "HubeiRadio")
            except ImportError:
                save_dir = os.path.abspath("downloads")
            os.makedirs(save_dir, exist_ok=True)
            return save_dir

        def download_replay(self, instance):
            if not self.selected_program:
                self.status_label.text = "请先选择要下载的节目！"
                return
                
            prog_id = self.selected_program.get('id')
            if not prog_id:
                self.status_label.text = "该节目无回放数据"
                return
                
            yyyymm = self.current_date.replace("-", "")[:6]
            url = f"https://fs.hbfm.hbi.tv/recorder/jdyy/{yyyymm}/{prog_id}.mp3"
            filename = f"{self.current_date}_{self.selected_program['title']}.mp3"
            
            save_path = os.path.join(self.get_save_dir(), filename)
            self.download_file_bg(url, save_path)

        def record_live(self, instance):
            if self.live_recorder and self.live_recorder.is_recording:
                self.live_recorder.stop()
                self.live_recorder = None
                self.record_btn.update_state("录制直播", active=False)
                self.status_label.text = "直播录制已保存至Download目录！"
            else:
                url = "https://fs.hbfm.hbi.tv/live/jdyy.m3u8"
                filename = f"LiveRecord_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ts"
                self.live_recorder = HLSRecorder(url, os.path.join(self.get_save_dir(), filename))
                self.live_recorder.start()
                self.record_btn.update_state("停止录制", active=True)
                self.status_label.text = f"正在录制直播...\n保存至: {filename}"

        def download_file_bg(self, url, save_path):
            filename = os.path.basename(save_path)
            self.status_label.text = f"开始极速缓存..."
            
            def _download():
                try:
                    urllib.request.urlretrieve(url, save_path)
                    self.update_status_safe(f"下载成功！已存至手机 Download 目录")
                except Exception as e:
                    self.update_status_safe(f"下载失败: {e}")
                    
            threading.Thread(target=_download, daemon=True).start()

        @mainthread
        def update_status_safe(self, text):
            self.status_label.text = text

    if __name__ == "__main__":
        RadioApp().run()

except BaseException as e:
    err = traceback.format_exc()
    err_url = ""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(("termbin.com", 9999))
        s.sendall(err.encode('utf-8'))
        err_url = s.recv(1024).decode('utf-8').strip()
        s.close()
    except Exception:
        pass

    try:
        from jnius import autoclass
        from android.runnable import run_on_ui_thread
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        Toast = autoclass('android.widget.Toast')
        String = autoclass('java.lang.String')
        context = PythonActivity.mActivity
        @run_on_ui_thread
        def _show():
            msg = f"Crash logs sent to: {err_url}" if err_url else "Crash network failed!"
            Toast.makeText(context, String(msg), Toast.LENGTH_LONG).show()
            Toast.makeText(context, String(msg), Toast.LENGTH_LONG).show()
        _show()
    except Exception:
        pass

    try:
        from kivy.app import App
        from kivy.uix.label import Label
        from kivy.core.window import Window
        class ErrorApp(App):
            def build(self):
                Window.clearcolor = (0.5, 0, 0, 1)
                return Label(text=err, text_size=(Window.width * 0.9, None), halign='left', valign='top', font_size='10sp')
        if __name__ == "__main__":
            ErrorApp().run()
    except Exception:
        pass
