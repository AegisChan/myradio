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
    from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
    from kivymd.uix.slider import MDSlider
    from kivymd.uix.list import MDList, TwoLineRightIconListItem, IconRightWidget
    from kivy.clock import Clock
    from kivy.clock import mainthread
    from kivy.core.window import Window
    from kivy.utils import get_color_from_hex
    from kivy.uix.behaviors import ButtonBehavior
    
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
            self.size_hint_x = 1
            self.md_bg_color = bg_color
            self.radius = [8, 8, 8, 8]
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
                self.md_bg_color = (1, 1, 1, 0.35)
                self.label_widget.text_color = get_color_from_hex("#60A5FA")
            else:
                self.md_bg_color = (1, 1, 1, 0.15)
                self.label_widget.text_color = (1, 1, 1, 0.9)

    class ClickableBanner(ButtonBehavior, MDBoxLayout):
        pass

    # 自定义紧凑且偏左的节目列表项
    class ProgramListItem(MDCard):
        def __init__(self, prog, app_instance, **kwargs):
            super().__init__(**kwargs)
            self.prog = prog
            self.app = app_instance
            self.size_hint_y = None
            self.height = "54dp"
            self.md_bg_color = (0, 0, 0, 0)
            self.elevation = 0
            self.ripple_behavior = True
            self.padding = ["20dp", "8dp", "20dp", "8dp"]
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
            
            # 彻底修复图标变方块的问题：保留所有包含 'Icon' 字样的字体样式
            for style in self.theme_cls.font_styles.keys():
                if "Icon" not in style:
                    self.theme_cls.font_styles[style][0] = "CustomFont"
                    orig_size = self.theme_cls.font_styles[style][1]
                    self.theme_cls.font_styles[style][1] = int(orig_size * 0.9)
            
            self.player = get_player()
            self.live_recorder = None
            self.current_date = datetime.now().strftime('%Y-%m-%d')
            self.schedule_data = []
            self.selected_program = None
            self.list_item_widgets = []
            self.is_seeking = False
            
            self.screen = MDScreen()
            
            # 全局背景图 (底层)
            bg_image = FitImage(source="background.png")
            self.screen.add_widget(bg_image)
            
            # 全局透明遮罩，保证无论切到哪个标签都能看到背景图
            overlay = MDBoxLayout(md_bg_color=(0.0, 0.0, 0.05, 0.35), orientation='vertical')
            self.screen.add_widget(overlay)
            
            # 顶部导航栏 (无多余图标)
            self.toolbar = MDTopAppBar(
                title="湖北经典音乐广播",
                elevation=0,
                md_bg_color=(0, 0, 0, 0.15),
                specific_text_color=(1, 1, 1, 1)
            )
            overlay.add_widget(self.toolbar)
            
            # --- 使用自定义 ScreenManager 代替死板的 MDBottomNavigation ---
            # 这可以保证背景全透明，并且高度完全受控
            self.sm = ScreenManager(transition=FadeTransition(duration=0.2))
            
            # === TAB 1: 频道大厅 ===
            screen_radio = Screen(name='screen_radio')
            tab1_layout = MDBoxLayout(orientation="vertical")
            
            # 日期选择横幅
            self.date_banner = ClickableBanner(
                orientation="horizontal", 
                size_hint_y=None, 
                height="48dp",
                md_bg_color=(1, 1, 1, 0.1),
                padding=["20dp", "0dp", "20dp", "0dp"]
            )
            self.date_banner.bind(on_release=self.open_date_menu)
            self.date_label = MDLabel(
                text=f"📅 当前日期：{self.current_date} (今天)   [点击切换]",
                halign="center",
                valign="center",
                theme_text_color="Custom",
                text_color=(1, 1, 1, 0.9),
                font_style="Body2"
            )
            self.date_banner.add_widget(self.date_label)
            tab1_layout.add_widget(self.date_banner)
            
            # 节目列表
            scroll = ScrollView()
            self.list_layout = MDBoxLayout(orientation="vertical", adaptive_height=True, spacing="2dp", padding=["0dp", "5dp", "0dp", "5dp"])
            scroll.add_widget(self.list_layout)
            tab1_layout.add_widget(scroll)
            
            # 底部控制台 (含进度条)
            bottom_container = MDBoxLayout(
                size_hint_y=None, 
                padding=["15dp", "5dp", "15dp", "15dp"],
                md_bg_color=(0, 0, 0, 0.4),
                orientation="vertical",
                spacing="5dp"
            )
            bottom_container.bind(minimum_height=bottom_container.setter('height'))
            
            # 进度条及时间显示
            slider_layout = MDBoxLayout(orientation="horizontal", size_hint_y=None, height="30dp", spacing="10dp")
            self.time_current = MDLabel(text="00:00", size_hint_x=None, width="40dp", halign="center", theme_text_color="Custom", text_color=(1,1,1,0.7), font_style="Caption")
            self.slider = MDSlider(min=0, max=100, value=0, color=get_color_from_hex("#60A5FA"), hint=False)
            self.slider.bind(on_touch_down=self.on_slider_down, on_touch_up=self.on_slider_up)
            self.time_total = MDLabel(text="00:00", size_hint_x=None, width="40dp", halign="center", theme_text_color="Custom", text_color=(1,1,1,0.7), font_style="Caption")
            
            slider_layout.add_widget(self.time_current)
            slider_layout.add_widget(self.slider)
            slider_layout.add_widget(self.time_total)
            bottom_container.add_widget(slider_layout)
            
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
            
            # 4个均匀分布的按键
            btn_grid = MDGridLayout(cols=2, spacing="15dp", size_hint_y=None)
            btn_grid.bind(minimum_height=btn_grid.setter('height'))
            glass_color = (1, 1, 1, 0.15)
            
            self.play_btn = CustomRectBtn("播放回放", glass_color, self.toggle_play)
            self.download_btn = CustomRectBtn("极速缓存", glass_color, self.download_replay)
            self.live_btn = CustomRectBtn("播放直播", glass_color, self.play_live)
            self.record_btn = CustomRectBtn("录制直播", glass_color, self.record_live)
            
            btn_grid.add_widget(self.play_btn)
            btn_grid.add_widget(self.download_btn)
            btn_grid.add_widget(self.live_btn)
            btn_grid.add_widget(self.record_btn)
            
            bottom_container.add_widget(btn_grid)
            tab1_layout.add_widget(bottom_container)
            screen_radio.add_widget(tab1_layout)
            self.sm.add_widget(screen_radio)
            
            # === TAB 2: 本地播放中心 ===
            screen_local = Screen(name='screen_local')
            tab2_layout = MDBoxLayout(orientation="vertical")
            
            tab2_top = MDBoxLayout(orientation="horizontal", size_hint_y=None, height="48dp", padding=["20dp", "0dp", "20dp", "0dp"], md_bg_color=(1, 1, 1, 0.1))
            tab2_top.add_widget(MDLabel(text="我下载的节目", font_style="H6", theme_text_color="Custom", text_color=(1,1,1,0.9)))
            refresh_btn = CustomRectBtn("刷新列表", (1,1,1,0.15), self.load_local_files)
            refresh_btn.size_hint_x = None
            refresh_btn.width = "100dp"
            refresh_btn.height = "32dp"
            refresh_btn.pos_hint = {'center_y': .5}
            tab2_top.add_widget(refresh_btn)
            tab2_layout.add_widget(tab2_top)
            
            local_scroll = ScrollView()
            self.local_list = MDList()
            local_scroll.add_widget(self.local_list)
            tab2_layout.add_widget(local_scroll)
            
            screen_local.add_widget(tab2_layout)
            self.sm.add_widget(screen_local)
            
            overlay.add_widget(self.sm)
            
            # === 自定义紧凑且全透明背景的底边栏 ===
            self.tab_bar = MDBoxLayout(
                orientation="horizontal",
                size_hint_y=None,
                height="45dp", # 比原生的 56dp 小很多，节省空间
                md_bg_color=(0, 0, 0, 0.6) # 黑色半透明，与背景完美融合
            )
            
            self.tab_btn_radio = CustomRectBtn("频道大厅", (1,1,1,0.25), lambda x: self.switch_tab('screen_radio'))
            self.tab_btn_radio.radius = [0, 0, 0, 0] # 纯平无圆角
            self.tab_btn_radio.label_widget.text_color = get_color_from_hex("#60A5FA") # 默认选中高亮
            
            self.tab_btn_local = CustomRectBtn("本地播放", (0,0,0,0), lambda x: self.switch_tab('screen_local'))
            self.tab_btn_local.radius = [0, 0, 0, 0]
            
            self.tab_bar.add_widget(self.tab_btn_radio)
            self.tab_bar.add_widget(self.tab_btn_local)
            
            overlay.add_widget(self.tab_bar)
            
            self.init_date_menu()
            Clock.schedule_once(lambda dt: self.load_schedule(self.current_date), 0.5)
            
            # 进度条定时器
            Clock.schedule_interval(self.update_progress, 1.0)
            
            return self.screen

        def switch_tab(self, tab_name):
            self.sm.current = tab_name
            if tab_name == 'screen_radio':
                self.tab_btn_radio.md_bg_color = (1, 1, 1, 0.25)
                self.tab_btn_radio.label_widget.text_color = get_color_from_hex("#60A5FA")
                self.tab_btn_local.md_bg_color = (0, 0, 0, 0)
                self.tab_btn_local.label_widget.text_color = (1, 1, 1, 0.9)
            else:
                self.tab_btn_local.md_bg_color = (1, 1, 1, 0.25)
                self.tab_btn_local.label_widget.text_color = get_color_from_hex("#60A5FA")
                self.tab_btn_radio.md_bg_color = (0, 0, 0, 0)
                self.tab_btn_radio.label_widget.text_color = (1, 1, 1, 0.9)
                self.load_local_files(None)

        def get_save_dir(self):
            try:
                from android.storage import primary_external_storage_path
                save_dir = os.path.join(primary_external_storage_path(), "Download", "HubeiRadio")
            except ImportError:
                save_dir = os.path.abspath("downloads")
            os.makedirs(save_dir, exist_ok=True)
            return save_dir

        def load_local_files(self, instance):
            self.local_list.clear_widgets()
            d = self.get_save_dir()
            try:
                files = os.listdir(d)
                files.sort(reverse=True) # 最新的在前
                count = 0
                for f in files:
                    if f.endswith(".mp3") or f.endswith(".ts"):
                        count += 1
                        fp = os.path.join(d, f)
                        sz = os.path.getsize(fp) / (1024*1024)
                        
                        item = TwoLineRightIconListItem(
                            text=f,
                            secondary_text=f"大小: {sz:.1f} MB",
                            theme_text_color="Custom",
                            text_color=(1, 1, 1, 0.9),
                            secondary_theme_text_color="Custom",
                            secondary_text_color=(1, 1, 1, 0.6),
                            bg_color=(0, 0, 0, 0.2)
                        )
                        # 右侧删除按钮
                        del_icon = IconRightWidget(
                            icon="trash-can-outline",
                            theme_text_color="Custom",
                            text_color=(1, 0.3, 0.3, 0.9)
                        )
                        del_icon.bind(on_release=lambda x, p=fp, i=item: self.delete_local_file(p, i))
                        item.add_widget(del_icon)
                        item.bind(on_release=lambda x, p=fp: self.play_local_file(p))
                        self.local_list.add_widget(item)
                if count == 0:
                    self.local_list.add_widget(MDLabel(
                        text=f"暂无下载的节目\n(如已下载，请确认是否有权限读取)\n路径:\n{d}", 
                        halign="center", 
                        theme_text_color="Custom", 
                        text_color=(1,1,1,0.6), 
                        size_hint_y=None, 
                        height="120dp"
                    ))
            except Exception as e:
                self.local_list.add_widget(MDLabel(text=f"读取失败: {e}", halign="center", theme_text_color="Custom", text_color=(1,0,0,0.8)))

        def delete_local_file(self, filepath, item):
            try:
                if self.player.is_playing():
                    self.stop_all()
                os.remove(filepath)
                self.local_list.remove_widget(item)
            except Exception as e:
                self.status_label.text = f"删除失败: {e}"

        def play_local_file(self, filepath):
            self.stop_all()
            self.status_label.text = f"正在播放本地文件..."
            self.player.play(filepath)
            self.set_keep_screen_on(True)

        def on_slider_down(self, instance, touch):
            if instance.collide_point(*touch.pos):
                self.is_seeking = True

        def on_slider_up(self, instance, touch):
            if self.is_seeking and instance.collide_point(*touch.pos):
                if self.player and self.player.get_duration() > 0:
                    target_ms = (instance.value / 100.0) * self.player.get_duration()
                    self.player.seek(target_ms)
                self.is_seeking = False

        def format_time(self, ms):
            s = int(ms / 1000)
            m = s // 60
            s = s % 60
            return f"{m:02d}:{s:02d}"

        def update_progress(self, dt):
            if self.player and self.player.is_playing() and not self.is_seeking:
                pos = self.player.get_position()
                dur = self.player.get_duration()
                if dur > 0:
                    self.slider.value = (pos / dur) * 100
                    self.time_current.text = self.format_time(pos)
                    self.time_total.text = self.format_time(dur)

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
            self.date_label.text = f"📅 当前日期：{label}   [点击切换]"
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
                    item.md_bg_color = (1, 1, 1, 0.25)
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

        def download_replay(self, instance):
            if not self.selected_program:
                self.status_label.text = "请先选择要极速缓存的节目！"
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
                self.status_label.text = "直播录制已保存，请前往【本地播放】查看"
            else:
                url = "https://fs.hbfm.hbi.tv/live/jdyy.m3u8"
                filename = f"LiveRecord_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ts"
                self.live_recorder = HLSRecorder(url, os.path.join(self.get_save_dir(), filename))
                self.live_recorder.start()
                self.record_btn.update_state("停止录制", active=True)
                self.status_label.text = f"🔴 正在录制直播..."

        def download_file_bg(self, url, save_path):
            filename = os.path.basename(save_path)
            self.status_label.text = f"开始极速缓存..."
            
            def _download():
                try:
                    urllib.request.urlretrieve(url, save_path)
                    self.update_status_safe(f"✅ 下载成功！请前往【本地播放】查看")
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
