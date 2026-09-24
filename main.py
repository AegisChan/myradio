import traceback

try:
    from kivy.core.text import LabelBase
    # 全局注册中文字体，解决所有中文变方块的问题
    LabelBase.register(name="SimHei", fn_regular="simhei.ttf")
    
    from kivymd.app import MDApp
    from kivymd.uix.screen import MDScreen
    from kivymd.uix.boxlayout import MDBoxLayout
    from kivymd.uix.toolbar import MDTopAppBar
    from kivymd.uix.list import MDList, TwoLineAvatarIconListItem, IconLeftWidget, IconRightWidget
    from kivymd.uix.menu import MDDropdownMenu
    from kivymd.uix.button import MDFloatingActionButton, MDIconButton
    from kivymd.uix.label import MDLabel
    from kivymd.uix.card import MDCard
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
    
    class ProgramListItem(TwoLineAvatarIconListItem):
        def __init__(self, prog, app_instance, **kwargs):
            super().__init__(**kwargs)
            self.prog = prog
            self.app = app_instance
            self.text = f"{prog['time']} - {prog['title']}"
            self.secondary_text = f"🎙 主播: {prog['host']}"
            
            # 默认颜色
            self.theme_text_color = "Custom"
            self.text_color = self.app.theme_cls.text_color
            
            # 左侧音乐图标
            self.icon_left = IconLeftWidget(icon="music-circle-outline")
            self.add_widget(self.icon_left)
            
            # 点击事件
            self.bind(on_release=self.on_click)
            
        def on_click(self, *args):
            self.app.on_program_select(self.prog, self)

    class RadioApp(MDApp):
        def build(self):
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.INTERNET, Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])
            except Exception:
                pass

            # 设置高端优雅的主题配色
            self.theme_cls.material_style = "M3" # 引入 Material 3 风格
            self.theme_cls.theme_style = "Dark"
            self.theme_cls.primary_palette = "Indigo" # 靛蓝色，高级感
            self.theme_cls.accent_palette = "Teal"
            
            # 强制替换所有 Material Design 的字体为我们的中文字体
            for style in self.theme_cls.font_styles.keys():
                self.theme_cls.font_styles[style][0] = "SimHei"
            
            self.player = get_player()
            self.live_recorder = None
            self.current_date = datetime.now().strftime('%Y-%m-%d')
            self.schedule_data = []
            self.selected_program = None
            self.list_item_widgets = []
            
            self.screen = MDScreen()
            # 使用稍微亮一点的深色背景，而不是纯黑
            self.screen.md_bg_color = get_color_from_hex("#121212")
            
            layout = MDBoxLayout(orientation='vertical')
            
            # 顶部导航栏 (M3风格)
            self.toolbar = MDTopAppBar(
                title="湖北经典音乐广播 (今天)",
                elevation=2,
                md_bg_color=self.theme_cls.primary_color,
                right_action_items=[["calendar-month", lambda x: self.open_date_menu(x)]]
            )
            layout.add_widget(self.toolbar)
            
            # 节目列表
            scroll = ScrollView()
            self.list_view = MDList()
            scroll.add_widget(self.list_view)
            layout.add_widget(scroll)
            
            # 底部控制台卡片 (圆角浮动卡片设计)
            bottom_container = MDBoxLayout(
                size_hint_y=None, 
                height="100dp",
                padding=["15dp", "10dp", "15dp", "15dp"]
            )
            
            control_card = MDCard(
                size_hint=(1, 1), 
                padding="15dp",
                spacing="15dp",
                elevation=2,
                radius=[25, 25, 25, 25], # 圆角卡片
                md_bg_color=get_color_from_hex("#1E1E2E")
            )
            
            # 左侧状态文本
            self.status_label = MDLabel(
                text="🎵 准备就绪，请选择节目", 
                halign="left", 
                valign="center",
                theme_text_color="Custom",
                text_color=get_color_from_hex("#A6ADC8"),
                size_hint_x=1,
                font_style="Caption"
            )
            control_card.add_widget(self.status_label)
            
            # 下载/缓存按钮
            self.download_btn = MDIconButton(
                icon="download-circle", 
                theme_text_color="Custom",
                text_color=self.theme_cls.accent_color,
                icon_size="48sp",
                on_release=self.start_cache_or_record
            )
            control_card.add_widget(self.download_btn)

            # 主播放按钮
            self.play_btn = MDFloatingActionButton(
                icon="play", 
                md_bg_color=self.theme_cls.primary_color,
                elevation=2,
                on_release=self.toggle_play
            )
            control_card.add_widget(self.play_btn)
            
            bottom_container.add_widget(control_card)
            layout.add_widget(bottom_container)
            self.screen.add_widget(layout)
            
            self.init_date_menu()
            Clock.schedule_once(lambda dt: self.load_schedule(self.current_date), 0.5)
            
            return self.screen

        def set_keep_screen_on(self, keep_on):
            # 安卓专用：控制屏幕常亮
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
                background_color=get_color_from_hex("#1E1E2E")
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
            self.status_label.text = "🔄 正在获取节目单..."
            
            def _fetch():
                data = get_daily_schedule(date_str)
                self.update_ui_schedule(data)
                
            threading.Thread(target=_fetch, daemon=True).start()

        @mainthread
        def update_ui_schedule(self, data):
            self.schedule_data = data
            self.list_view.clear_widgets()
            self.list_item_widgets.clear()
            
            if not data:
                self.status_label.text = "❌ 获取失败"
                return
                
            for prog in data:
                item = ProgramListItem(prog=prog, app_instance=self)
                self.list_item_widgets.append(item)
                self.list_view.add_widget(item)
                
            self.status_label.text = "✅ 节目单已更新"

        def on_program_select(self, prog, clicked_item):
            self.selected_program = prog
            self.status_label.text = f"📍 已选中: {prog['title']}"
            
            # 更新列表 UI 选中状态：取消所有高亮，高亮当前
            for item in self.list_item_widgets:
                if item == clicked_item:
                    item.text_color = self.theme_cls.primary_color
                    item.icon_left.icon = "music-circle"
                    item.icon_left.text_color = self.theme_cls.primary_color
                    item.icon_left.theme_text_color = "Custom"
                else:
                    item.text_color = self.theme_cls.text_color
                    item.icon_left.icon = "music-circle-outline"
                    item.icon_left.theme_text_color = "Primary"

        def toggle_play(self, instance):
            if self.player.is_playing():
                self.player.stop()
                self.play_btn.icon = "play"
                self.play_btn.md_bg_color = self.theme_cls.primary_color
                self.status_label.text = "⏹ 已停止播放"
                self.set_keep_screen_on(False) # 停止时关闭屏幕常亮
                return
                
            if not self.selected_program:
                self.status_label.text = "⚠️ 请先选择一个节目！"
                return
                
            if self.current_date != datetime.now().strftime('%Y-%m-%d') and not self.selected_program.get('id'):
                self.status_label.text = "⚠️ 离线数据无法播放回放！"
                return
                
            prog_id = self.selected_program.get('id')
            if prog_id:
                yyyymm = self.current_date.replace("-", "")[:6]
                replay_url = f"https://fs.hbfm.hbi.tv/recorder/jdyy/{yyyymm}/{prog_id}.mp3"
                self.status_label.text = f"🎧 正在缓冲: {self.selected_program['title']}..."
                self.player.play(replay_url)
                self.play_btn.icon = "stop"
                self.play_btn.md_bg_color = get_color_from_hex("#E53935") # 红色停止键
                self.set_keep_screen_on(True) # 播放时保持屏幕点亮
            else:
                self.status_label.text = "📡 正在连接直播源..."
                self.player.play("https://fs.hbfm.hbi.tv/live/jdyy.m3u8")
                self.play_btn.icon = "stop"
                self.play_btn.md_bg_color = get_color_from_hex("#E53935")
                self.set_keep_screen_on(True)

        def start_cache_or_record(self, instance):
            if not self.selected_program:
                self.status_label.text = "⚠️ 请先选择节目！"
                return
                
            prog_id = self.selected_program.get('id')
            
            try:
                from android.storage import primary_external_storage_path
                save_dir = os.path.join(primary_external_storage_path(), "Download", "HubeiRadio")
            except ImportError:
                save_dir = os.path.abspath("downloads")
                
            os.makedirs(save_dir, exist_ok=True)
            
            if prog_id:
                yyyymm = self.current_date.replace("-", "")[:6]
                url = f"https://fs.hbfm.hbi.tv/recorder/jdyy/{yyyymm}/{prog_id}.mp3"
                filename = f"{self.current_date}_{self.selected_program['title']}.mp3"
                self.download_file_bg(url, os.path.join(save_dir, filename))
            else:
                if self.live_recorder and self.live_recorder.is_recording:
                    self.live_recorder.stop()
                    self.live_recorder = None
                    self.download_btn.icon = "download-circle"
                    self.status_label.text = "✅ 直播录制已保存！"
                else:
                    url = "https://fs.hbfm.hbi.tv/live/jdyy.m3u8"
                    filename = f"LiveRecord_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ts"
                    self.live_recorder = HLSRecorder(url, os.path.join(save_dir, filename))
                    self.live_recorder.start()
                    self.download_btn.icon = "stop-circle-outline"
                    self.status_label.text = f"🔴 正在录制直播...\n保存至: {filename}"

        def download_file_bg(self, url, save_path):
            filename = os.path.basename(save_path)
            self.status_label.text = f"⬇️ 开始极速缓存..."
            
            def _download():
                try:
                    urllib.request.urlretrieve(url, save_path)
                    self.update_status_safe(f"✅ 下载成功！\n已存至 Download 目录")
                except Exception as e:
                    self.update_status_safe(f"❌ 下载失败: {e}")
                    
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
