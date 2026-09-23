import traceback

try:
    from kivymd.app import MDApp
    from kivymd.uix.screen import MDScreen
    from kivymd.uix.boxlayout import MDBoxLayout
    from kivymd.uix.toolbar import MDTopAppBar
    from kivymd.uix.list import MDList, TwoLineListItem
    from kivymd.uix.menu import MDDropdownMenu
    from kivymd.uix.button import MDFloatingActionButton
    from kivymd.uix.label import MDLabel
    from kivymd.uix.card import MDCard
    from kivy.uix.scrollview import ScrollView
    from kivy.clock import Clock
    from kivy.clock import mainthread
    from kivy.core.window import Window
    
    from datetime import datetime, timedelta
    import threading
    import os
    import urllib.request
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context
    
    from radio_api import get_daily_schedule
    from android_player import get_player
    from hls_recorder import HLSRecorder
    
    class RadioApp(MDApp):
        def build(self):
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.INTERNET, Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])
            except Exception:
                pass

            self.theme_cls.theme_style = "Dark"
            self.theme_cls.primary_palette = "BlueGray"
            self.theme_cls.accent_palette = "Teal"
            
            self.player = get_player()
            self.live_recorder = None
            self.current_date = datetime.now().strftime('%Y-%m-%d')
            self.schedule_data = []
            self.selected_program = None
            
            self.screen = MDScreen()
            layout = MDBoxLayout(orientation='vertical')
            
            # 顶部导航栏
            self.toolbar = MDTopAppBar(
                title="湖北经典音乐广播 (今天)",
                elevation=4,
                right_action_items=[["calendar", lambda x: self.open_date_menu(x)]]
            )
            layout.add_widget(self.toolbar)
            
            # 节目列表
            scroll = ScrollView()
            self.list_view = MDList()
            scroll.add_widget(self.list_view)
            layout.add_widget(scroll)
            
            # 底部控制台
            control_card = MDCard(
                size_hint=(1, None), 
                height="80dp", 
                padding="15dp",
                spacing="10dp",
                elevation=4, 
                md_bg_color=self.theme_cls.bg_darkest
            )
            
            self.status_label = MDLabel(
                text="准备就绪", 
                halign="left", 
                theme_text_color="Secondary",
                size_hint_x=1
            )
            control_card.add_widget(self.status_label)
            
            # 播放控制
            self.play_btn = MDFloatingActionButton(
                icon="play", 
                md_bg_color=self.theme_cls.primary_color,
                on_release=self.toggle_play
            )
            control_card.add_widget(self.play_btn)
            
            # 下载/缓存按钮
            self.download_btn = MDFloatingActionButton(
                icon="download", 
                md_bg_color=self.theme_cls.accent_color,
                on_release=self.start_cache_or_record
            )
            control_card.add_widget(self.download_btn)
            
            layout.add_widget(control_card)
            self.screen.add_widget(layout)
            
            self.init_date_menu()
            
            # 首次加载今天数据
            Clock.schedule_once(lambda dt: self.load_schedule(self.current_date), 0.5)
            
            return self.screen

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
            self.list_view.clear_widgets()
            
            if not data:
                self.status_label.text = "获取失败"
                return
                
            for prog in data:
                item = TwoLineListItem(
                    text=f"{prog['time']} - {prog['title']}",
                    secondary_text=f"主持: {prog['host']}",
                    on_release=lambda x, p=prog: self.on_program_select(p)
                )
                self.list_view.add_widget(item)
                
            self.status_label.text = "节目单加载完成"

        def on_program_select(self, prog):
            self.selected_program = prog
            self.status_label.text = f"已选中: {prog['title']}"

        def toggle_play(self, instance):
            if self.player.is_playing():
                self.player.stop()
                self.play_btn.icon = "play"
                self.status_label.text = "已停止播放"
                return
                
            # 播放逻辑
            if not self.selected_program:
                self.status_label.text = "请先选择一个节目！"
                return
                
            # 如果选中的是以前的节目，并且没有ID，说明是固化数据
            if self.current_date != datetime.now().strftime('%Y-%m-%d') and not self.selected_program.get('id'):
                self.status_label.text = "离线数据无法播放回放！"
                return
                
            prog_id = self.selected_program.get('id')
            if prog_id:
                # 播放回放
                yyyymm = self.current_date.replace("-", "")[:6]
                replay_url = f"https://fs.hbfm.hbi.tv/recorder/jdyy/{yyyymm}/{prog_id}.mp3"
                
                self.status_label.text = f"正在缓冲回放: {self.selected_program['title']}..."
                self.player.play(replay_url)
                self.play_btn.icon = "stop"
            else:
                # 播放直播 (今天并且没有有效id，或者是正在直播的)
                self.status_label.text = "正在连接直播源..."
                self.player.play("https://fs.hbfm.hbi.tv/live/jdyy.m3u8")
                self.play_btn.icon = "stop"

        def start_cache_or_record(self, instance):
            if not self.selected_program:
                self.status_label.text = "请先选择要下载的节目！"
                return
                
            prog_id = self.selected_program.get('id')
            
            try:
                from android.storage import primary_external_storage_path
                save_dir = os.path.join(primary_external_storage_path(), "Download", "HubeiRadio")
            except ImportError:
                save_dir = os.path.abspath("downloads")
                
            os.makedirs(save_dir, exist_ok=True)
            
            if prog_id:
                # 下载回放 MP3
                yyyymm = self.current_date.replace("-", "")[:6]
                url = f"https://fs.hbfm.hbi.tv/recorder/jdyy/{yyyymm}/{prog_id}.mp3"
                filename = f"{self.current_date}_{self.selected_program['title']}.mp3"
                self.download_file_bg(url, os.path.join(save_dir, filename))
            else:
                # 录制直播
                if self.live_recorder and self.live_recorder.is_recording:
                    self.live_recorder.stop()
                    self.live_recorder = None
                    self.download_btn.icon = "download"
                    self.status_label.text = "直播录制已保存！"
                else:
                    url = "https://fs.hbfm.hbi.tv/live/jdyy.m3u8"
                    filename = f"LiveRecord_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ts"
                    self.live_recorder = HLSRecorder(url, os.path.join(save_dir, filename))
                    self.live_recorder.start()
                    self.download_btn.icon = "stop-circle"
                    self.status_label.text = f"正在录制直播...\n保存至: {filename}"

        def download_file_bg(self, url, save_path):
            filename = os.path.basename(save_path)
            self.status_label.text = f"开始极速缓存: {filename}..."
            
            def _download():
                try:
                    urllib.request.urlretrieve(url, save_path)
                    self.update_status_safe(f"下载成功！\n已保存至: {save_path}")
                except Exception as e:
                    self.update_status_safe(f"下载失败: {e}")
                    
            threading.Thread(target=_download, daemon=True).start()

        @mainthread
        def update_status_safe(self, text):
            self.status_label.text = text

    if __name__ == "__main__":
        RadioApp().run()

except Exception as e:
    err = traceback.format_exc()
    # 尝试写入手机安全目录
    try:
        from jnius import autoclass
        PythonActivity = autoclass('org.kivy.android.PythonActivity')
        context = PythonActivity.mActivity
        ext_dir = context.getExternalFilesDir(None).getAbsolutePath()
        with open(ext_dir + "/crash.txt", "w") as f:
            f.write(err)
    except Exception:
        pass

    from kivy.app import App
    from kivy.uix.label import Label
    from kivy.core.window import Window

    class ErrorApp(App):
        def build(self):
            Window.clearcolor = (0.5, 0, 0, 1) # 深红色背景
            # 缩放字体以确保大部分内容可见
            return Label(text=err, text_size=(Window.width * 0.9, None), halign='left', valign='top', font_size='10sp')

    if __name__ == "__main__":
        ErrorApp().run()
