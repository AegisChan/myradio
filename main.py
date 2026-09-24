import traceback

try:
    from kivy.core.text import LabelBase
    # 全局注册中文字体（使用更细腻的邓线 Light）
    LabelBase.register(name="CustomFont", fn_regular="font.ttf")
    
    from kivymd.app import MDApp
    from kivymd.uix.screen import MDScreen
    from kivymd.uix.boxlayout import MDBoxLayout
    from kivymd.uix.toolbar import MDTopAppBar
    from kivymd.uix.list import MDList, TwoLineAvatarIconListItem, IconLeftWidget
    from kivymd.uix.menu import MDDropdownMenu
    from kivymd.uix.button import MDFillRoundFlatButton, MDFillRoundFlatIconButton
    from kivymd.uix.label import MDLabel
    from kivymd.uix.card import MDCard
    from kivy.uix.image import Image
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
            self.secondary_text = f"主播: {prog['host']}"
            
            # 使用透明背景
            self.bg_color = (0, 0, 0, 0)
            
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

            # 设置主题
            self.theme_cls.material_style = "M3"
            self.theme_cls.theme_style = "Dark"
            self.theme_cls.primary_palette = "DeepPurple"
            self.theme_cls.accent_palette = "Pink"
            
            # 强制替换中文字体，但保留 Material Icons 图标字体！(解决方块图标问题)
            for style in self.theme_cls.font_styles.keys():
                if style != "Icons":
                    self.theme_cls.font_styles[style][0] = "CustomFont"
            
            self.player = get_player()
            self.live_recorder = None
            self.current_date = datetime.now().strftime('%Y-%m-%d')
            self.schedule_data = []
            self.selected_program = None
            self.list_item_widgets = []
            
            self.screen = MDScreen()
            
            # 1. 核心需求：背景图片
            bg_image = Image(source="background.png", allow_stretch=True, keep_ratio=False)
            self.screen.add_widget(bg_image)
            
            # 增加一个半透明黑色遮罩层，让背景图片变暗，以免干扰文字显示
            overlay = MDBoxLayout(md_bg_color=(0, 0, 0, 0.5), orientation='vertical')
            self.screen.add_widget(overlay)
            
            # 2. 顶部导航栏 (毛玻璃/半透明效果)
            self.toolbar = MDTopAppBar(
                title="湖北经典音乐广播 (今天)",
                elevation=0,
                md_bg_color=(0, 0, 0, 0.3), # 半透明
                right_action_items=[["calendar-month", lambda x: self.open_date_menu(x)]]
            )
            overlay.add_widget(self.toolbar)
            
            # 3. 节目列表
            scroll = ScrollView()
            self.list_view = MDList()
            scroll.add_widget(self.list_view)
            overlay.add_widget(scroll)
            
            # 4. 底部控制台卡片 (半透明扁平化设计)
            bottom_container = MDBoxLayout(
                size_hint_y=None, 
                height="130dp",
                padding=["15dp", "10dp", "15dp", "15dp"],
                md_bg_color=(0, 0, 0, 0.4)
            )
            
            control_layout = MDBoxLayout(orientation="vertical", spacing="10dp")
            
            # 状态文本
            self.status_label = MDLabel(
                text="准备就绪，请选择节目", 
                halign="center", 
                valign="center",
                theme_text_color="Custom",
                text_color=(1, 1, 1, 0.8),
                size_hint_y=None,
                height="30dp",
                font_style="Caption"
            )
            control_layout.add_widget(self.status_label)
            
            # 按钮行 (排列整齐的扁平矩形按钮)
            btn_row = MDBoxLayout(orientation="horizontal", spacing="15dp", size_hint_y=None, height="50dp")
            
            # 播放选中按键
            self.play_btn = MDFillRoundFlatIconButton(
                text="播放回放",
                icon="play-circle",
                size_hint_x=1,
                md_bg_color=self.theme_cls.primary_color,
                on_release=self.toggle_play
            )
            
            # 核心需求：播放直播专属按键
            self.live_btn = MDFillRoundFlatIconButton(
                text="播放直播",
                icon="radio",
                size_hint_x=1,
                md_bg_color=get_color_from_hex("#D81B60"), # 显眼的粉红色
                on_release=self.play_live
            )
            
            # 下载按键
            self.download_btn = MDFillRoundFlatIconButton(
                text="极速缓存",
                icon="download",
                size_hint_x=1,
                md_bg_color=get_color_from_hex("#00897B"), # 沉稳的绿色
                on_release=self.start_cache_or_record
            )
            
            btn_row.add_widget(self.play_btn)
            btn_row.add_widget(self.live_btn)
            btn_row.add_widget(self.download_btn)
            
            control_layout.add_widget(btn_row)
            bottom_container.add_widget(control_layout)
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
                background_color=(0.1, 0.1, 0.1, 0.9)
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
            self.list_item_widgets.clear()
            
            if not data:
                self.status_label.text = "获取失败"
                return
                
            for prog in data:
                item = ProgramListItem(prog=prog, app_instance=self)
                self.list_item_widgets.append(item)
                self.list_view.add_widget(item)
                
            self.status_label.text = "节目单加载完成"

        def on_program_select(self, prog, clicked_item):
            self.selected_program = prog
            self.status_label.text = f"已选中: {prog['title']}"
            
            # 更新列表 UI 选中状态，让选中的条目变得非常明显
            for item in self.list_item_widgets:
                if item == clicked_item:
                    item.bg_color = (1, 1, 1, 0.15) # 选中的背景微亮
                    item.text_color = self.theme_cls.accent_color
                    item.secondary_text_color = self.theme_cls.accent_color
                    item.icon_left.icon = "music-circle"
                    item.icon_left.text_color = self.theme_cls.accent_color
                    item.icon_left.theme_text_color = "Custom"
                else:
                    item.bg_color = (0, 0, 0, 0)
                    item.text_color = self.theme_cls.text_color
                    item.secondary_text_color = self.theme_cls.text_color
                    item.icon_left.icon = "music-circle-outline"
                    item.icon_left.theme_text_color = "Primary"

        def stop_all(self):
            if self.player.is_playing():
                self.player.stop()
            self.play_btn.icon = "play-circle"
            self.play_btn.text = "播放回放"
            self.live_btn.icon = "radio"
            self.live_btn.text = "播放直播"
            self.set_keep_screen_on(False)

        def play_live(self, instance):
            if self.player.is_playing() and self.live_btn.text == "停止直播":
                self.stop_all()
                self.status_label.text = "已停止直播"
                return
                
            self.stop_all()
            self.status_label.text = "正在连接直播源..."
            self.player.play("https://fs.hbfm.hbi.tv/live/jdyy.m3u8")
            self.live_btn.icon = "stop-circle"
            self.live_btn.text = "停止直播"
            self.set_keep_screen_on(True)

        def toggle_play(self, instance):
            if self.player.is_playing() and self.play_btn.text == "停止回放":
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
                self.play_btn.icon = "stop-circle"
                self.play_btn.text = "停止回放"
                self.set_keep_screen_on(True)
            else:
                self.status_label.text = "当前节目无回放资源，请点击'播放直播'"

        def start_cache_or_record(self, instance):
            if not self.selected_program:
                self.status_label.text = "请先选择要操作的节目！"
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
                    self.download_btn.icon = "download"
                    self.download_btn.text = "极速缓存"
                    self.status_label.text = "直播录制已保存至Download目录！"
                else:
                    url = "https://fs.hbfm.hbi.tv/live/jdyy.m3u8"
                    filename = f"LiveRecord_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ts"
                    self.live_recorder = HLSRecorder(url, os.path.join(save_dir, filename))
                    self.live_recorder.start()
                    self.download_btn.icon = "stop"
                    self.download_btn.text = "停止录制"
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
