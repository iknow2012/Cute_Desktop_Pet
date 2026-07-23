# -*- coding: utf-8 -*-
"""
桌宠程序 - 使用 tkinter + Pillow 实现
状态机:
  肝作业 (homework) ──1分钟无打扰──→ 睡觉 (sleeping)
  肝作业 (homework) ──点击──→ 肝作业被打扰 (homework_interrupted) ──5秒──→ 肝作业
  睡觉 (sleeping)   ──点击──→ 睡觉被打扰 (sleeping_interrupted)  ──5秒──→ 肝作业
"""

import tkinter as tk
import os
import time
import sys
import math as _m
import json
import threading

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import urllib.parse

try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont
except ImportError:
    print("错误: 需要 Pillow 库。请运行: pip install Pillow")
    sys.exit(1)


def _cos(r):
    return _m.cos(r)
def _sin(r):
    return _m.sin(r)


class DeskPet:
    # 状态常量
    HOMEWORK = "homework"
    HOMEWORK_INTERRUPTED = "homework_interrupted"
    SLEEPING = "sleeping"
    SLEEPING_INTERRUPTED = "sleeping_interrupted"

    # 状态对应的图片文件名
    STATE_IMAGES = {
        HOMEWORK: "肝作业.png",
        HOMEWORK_INTERRUPTED: "肝作业被打扰.png",
        SLEEPING: "睡觉.png",
        SLEEPING_INTERRUPTED: "睡觉被打扰.png",
    }

    # 状态说明文本（桌宠第一人称可爱风格，控制在一行）
    STATE_LABELS = {
        HOMEWORK: "肝作业了 一起加油哈！",
        HOMEWORK_INTERRUPTED: "干嘛戳我啦！",
        SLEEPING: "好困啊，.zZ..",
        SLEEPING_INTERRUPTED: "唔唔唔，干嘛吵醒我啊！",
    }

    # 过渡时间（秒）
    INTERRUPT_DURATION = 5       # 被打扰后恢复时间
    HOMEWORK_TO_SLEEP_DELAY = 30  # 肝作业持续多久后进入睡眠

    # 缩放比例（原图 2048x1152，缩小到 1/10）
    SCALE_RATIO = 0.1

    # ---- 气泡对话框 (ver1 移植) ----
    BUBBLE_FONT = ('Microsoft YaHei UI', 11)
    BUBBLE_FG = '#444444'
    BUBBLE_BG = '#ffffff'
    BUBBLE_BORDER = '#cccccc'
    BUBBLE_BORDER_W = 1
    BUBBLE_PAD_X = 16
    BUBBLE_PAD_Y = 10
    BUBBLE_TAIL = 8
    BUBBLE_TAIL_H = 10
    BUBBLE_MAX_W = 200
    BUBBLE_SHOW_DURATION = 3.0

    # ---- 翻译面板 ----
    TOGGLE_BAR_H = 18          # 底部折叠条高度
    PANEL_H = 52               # 翻译面板展开高度（适配小按钮）
    PANEL_EXPANDED = False     # 面板展开状态

    def __init__(self, root, image_dir=None):
        self.root = root

        # 程序根目录
        if getattr(sys, "frozen", False):
            self._base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        else:
            self._base_dir = os.path.dirname(os.path.abspath(__file__))

        # 图片目录
        if image_dir is None:
            image_dir = os.path.join(self._base_dir, "人物")
        self.image_dir = image_dir

        # ---------- 加载图片（需要先加载，后面要用到尺寸） ----------
        self.photo_images = {}  # ImageTk.PhotoImage 缓存
        self.raw_images = {}    # PIL Image 缓存
        self._load_all_images()

        # ---------- 窗口设置 ----------
        self.root.title("桌宠")                       # 窗口标题
        self.root.configure(bg="white")                # 白色背景
        self.root.attributes("-topmost", True)         # 置顶
        self.root.resizable(False, False)              # 固定大小
        # 窗口图标（使用 logo/logo.ico，与 exe 资源管理器图标一致）
        try:
            logo_path = os.path.join(self._base_dir, "logo", "logo.ico")
            img = Image.open(logo_path)
            img = img.resize((32, 32), Image.LANCZOS)
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            self._icon_img = ImageTk.PhotoImage(img)
            # -default 同时设置所有后续窗口
            self.root.tk.call("wm", "iconphoto", self.root, "-default", self._icon_img)
        except Exception:
            pass

        # ---------- 变量 ----------
        self.current_state = self.HOMEWORK
        self.homework_start_time = time.time()     # 本次进入肝作业的时间
        self.interrupt_start_time = None           # 被打扰的开始时间
        self.offset_x = 0
        self.offset_y = 0
        self.bubble_job = None                     # 气泡定时器

        # ---------- 界面 ----------
        self.canvas = tk.Canvas(
            self.root,
            highlightthickness=0,
            borderwidth=0,
            bg="white",
        )
        self.canvas.pack()

        # 获取首张图片的尺寸，计算正方形窗口大小
        first_img = self.photo_images[self.current_state]
        self.img_width = first_img.width()
        self.img_height = first_img.height()
        self.win_size = max(self.img_width, self.img_height)  # 1:1 正方形窗口
        self.canvas.config(width=self.win_size, height=self.win_size)

        # 图片下移到底部附近
        cx = (self.win_size - self.img_width) // 2
        cy = self.win_size - self.img_height - 8
        self.img_on_canvas = self.canvas.create_image(cx, cy, anchor="nw", image=first_img)

        # ---------- 翻译折叠面板（圆角按钮） ----------
        # 底部折叠条
        self.toggle_bar = tk.Frame(self.root, bg="#f0f0f0", height=self.TOGGLE_BAR_H, cursor="hand2")
        self.toggle_bar_container = tk.Frame(self.toggle_bar, bg="#f0f0f0")
        self.toggle_bar_container.pack(expand=True, fill=tk.BOTH)
        self.toggle_icon = tk.Label(self.toggle_bar_container, text="▲  展开翻译",
                                     bg="#f0f0f0", fg="#aaaaaa",
                                     font=("Microsoft YaHei UI", 8), cursor="hand2")
        self.toggle_icon.pack(expand=True, fill=tk.BOTH)
        self.toggle_bar.bind("<Button-1>", self.toggle_panel)
        self.toggle_icon.bind("<Button-1>", self.toggle_panel)

        # 翻译面板（默认隐藏）— 用 PIL 生成圆角按钮图片 + Label 展示
        self.translate_panel = tk.Frame(self.root, bg="white", height=self.PANEL_H)
        self._panel_btn_img = None  # 按钮图片，防 GC

        def _build_panel_btn():
            """生成圆角按钮图片放到面板中"""
            if self._panel_btn_img is not None:
                return
            img = self._make_rounded_btn_img("帮我翻译", 90, 28, 14,
                                              "#4A90D9", "#ffffff", 11)
            self._panel_btn_img = img
            lbl = tk.Label(self.translate_panel, image=img, bg="white", cursor="hand2")
            lbl.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
            lbl.bind("<Button-1>", lambda e: self.open_translate_window())
        self._build_panel_btn = _build_panel_btn

        # 重新规划 layout
        self.canvas.pack_forget()
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=False)
        self.toggle_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self._apply_win_size()

        # ---------- 事件绑定 ----------
        self.canvas.bind("<Button-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_drag)

        # 右键菜单退出
        self.root.bind("<Button-3>", self.show_context_menu)
        self.root.bind("<Control-Button-1>", self.show_context_menu)

        # ---------- 启动主循环 ----------
        self.update()

    # ======================== 图片加载 ========================

    def _load_all_images(self):
        """加载所有状态图片，按原比例缩小到 1/10，将透明背景映射为 transparent_color"""
        for state, filename in self.STATE_IMAGES.items():
            path = os.path.join(self.image_dir, filename)
            if not os.path.exists(path):
                print(f"警告: 图片不存在 {path}")
                continue
            pil_img = Image.open(path).convert("RGBA")
            # 按原比例等比例缩小
            new_w = int(pil_img.width * self.SCALE_RATIO)
            new_h = int(pil_img.height * self.SCALE_RATIO)
            pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)
            self.raw_images[state] = pil_img
            # 在白色背景上合成，去除透明通道
            tk_img = self._pil_to_tk_white_bg(pil_img)
            self.photo_images[state] = tk_img

    def _pil_to_tk_white_bg(self, pil_img):
        """将 PIL RGBA 图片在白色背景上合成，边缘抗锯齿自然融入白色"""
        rgb = pil_img.convert("RGB")
        bg = Image.new("RGB", rgb.size, "#FFFFFF")
        # 用 alpha 通道做蒙版合成
        a = pil_img.split()[3]
        result = Image.composite(rgb, bg, a)
        return ImageTk.PhotoImage(result)

    # ---- 圆角按钮图片生成（PIL 渲染，抗锯齿） ----

    def _make_rounded_btn_img(self, text, width, height, radius,
                              bg_color, fg_color="#ffffff",
                              font_size=13, bold=False):
        """用 PIL 生成圆角按钮图片（返回 PhotoImage，需持有引用防 GC）"""
        scale = 3
        w, h = width * scale, height * scale
        r = radius * scale

        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=r, fill=bg_color)

        try:
            font = ImageFont.truetype("msyh.ttc", font_size * scale)
        except Exception:
            try:
                font = ImageFont.truetype("msyhbd.ttc", font_size * scale)
            except Exception:
                font = ImageFont.load_default()

        cx, cy = w // 2, h // 2
        draw.text((cx, cy), text, font=font, fill=fg_color, anchor="mm")

        result = img.resize((width, height), Image.LANCZOS)
        return ImageTk.PhotoImage(result)

    def _make_rounded_btn_on_canvas(self, canvas, cx, cy, width, height, radius,
                                     text, bg_color, fg_color="#ffffff",
                                     font_size=12, command=None):
        """在 Canvas 上绘制一个圆角按钮（返回 (rect_id, text_id)）"""
        r = radius
        pts = []
        n = 12
        # 左上
        for i in range(n + 1):
            a = -90 + (i / n) * 90
            rad = a * _m.pi / 180
            pts.append((cx + r * _cos(rad), cy + r * _sin(rad)))
        # 右上
        for i in range(n + 1):
            a = (i / n) * 90
            rad = a * _m.pi / 180
            pts.append((cx + width - r + r * _cos(rad), cy + r * _sin(rad)))
        # 右下
        for i in range(n + 1):
            a = 90 + (i / n) * 90
            rad = a * _m.pi / 180
            pts.append((cx + width - r + r * _cos(rad), cy + height - r + r * _sin(rad)))
        # 左下
        for i in range(n + 1):
            a = 180 + (i / n) * 90
            rad = a * _m.pi / 180
            pts.append((cx + r * _cos(rad), cy + height - r + r * _sin(rad)))

        flat = []
        for p in pts:
            flat.extend([round(p[0], 1), round(p[1], 1)])

        rect_id = canvas.create_polygon(flat, fill=bg_color, outline="",
                                         width=0, smooth=True)
        txt_id = canvas.create_text(cx + width // 2, cy + height // 2,
                                     text=text, fill=fg_color,
                                     font=("Microsoft YaHei UI", font_size, "bold" if font_size >= 13 else "normal"),
                                     anchor=tk.CENTER)
        if command:
            canvas.tag_bind(rect_id, "<Button-1>", lambda e: command())
            canvas.tag_bind(txt_id, "<Button-1>", lambda e: command())
            canvas.config(cursor="hand2")
        return rect_id, txt_id

    # ======================== 气泡（画在主 Canvas 上，天然跟随）=======================

    def _show_bubble(self, text):
        """在主角画布上绘制气泡"""
        if self.bubble_job:
            self.root.after_cancel(self.bubble_job)
            self.bubble_job = None
        self._hide_bubble()

        c = self.canvas

        # 测量文字
        tid = c.create_text(0, 0, text=text, font=self.BUBBLE_FONT, anchor="nw")
        bb = c.bbox(tid)
        c.delete(tid)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]

        display = text
        if tw > self.BUBBLE_MAX_W:
            cpl = max(1, int(len(text) * self.BUBBLE_MAX_W / tw))
            lines = [text[i:i+cpl] for i in range(0, len(text), cpl)]
            display = "\n".join(lines)
            tid2 = c.create_text(0, 0, text=display, font=self.BUBBLE_FONT, anchor="nw")
            bb2 = c.bbox(tid2)
            c.delete(tid2)
            tw, th = bb2[2] - bb2[0], bb2[3] - bb2[1]

        bw = tw + self.BUBBLE_PAD_X * 2 + 2
        bh = th + self.BUBBLE_PAD_Y * 2 + 2
        tail = self.BUBBLE_TAIL
        tail_h = self.BUBBLE_TAIL_H
        r = 8

        # 角色在画布上的坐标
        coords = c.coords(self.img_on_canvas)
        ix, iy = int(coords[0]), int(coords[1])

        # 气泡定位：角色上方居中
        bx = ix + (self.img_width - bw) // 2
        by = iy - bh - tail_h + 2
        tail_down = True
        if by < 4:
            by = iy + self.img_height + 4  # 上方不够放下面
            tail_down = False

        # 圆角矩形（偏移到 (bx, by)）
        pts = self._rounded_rect_poly(bx, by, bx + bw, by + bh, r)
        c.create_polygon(pts, fill=self.BUBBLE_BG, outline=self.BUBBLE_BORDER,
                         width=self.BUBBLE_BORDER_W, smooth=False,
                         joinstyle="round", tags=("bubble",))

        # 三角尾巴
        tail_cx = bx + bw // 2
        if tail_down:  # 在上方 → 尾巴朝下
            ty = by + bh
            tail_pts = [tail_cx - tail, ty, tail_cx + tail, ty, tail_cx, ty + tail_h]
            c.create_polygon(tail_pts, fill=self.BUBBLE_BG, outline=self.BUBBLE_BORDER,
                             width=self.BUBBLE_BORDER_W, joinstyle="round", tags=("bubble",))
            c.create_line(tail_cx - tail + 1, ty, tail_cx + tail - 1, ty,
                          fill=self.BUBBLE_BG, width=self.BUBBLE_BORDER_W + 1, tags=("bubble",))
        else:  # 在下方 → 尾巴朝上
            ty = by
            tail_pts = [tail_cx - tail, ty, tail_cx + tail, ty, tail_cx, ty - tail_h]
            c.create_polygon(tail_pts, fill=self.BUBBLE_BG, outline=self.BUBBLE_BORDER,
                             width=self.BUBBLE_BORDER_W, joinstyle="round", tags=("bubble",))
            c.create_line(tail_cx - tail + 1, ty, tail_cx + tail - 1, ty,
                          fill=self.BUBBLE_BG, width=self.BUBBLE_BORDER_W + 1, tags=("bubble",))

        # 文字
        c.create_text(bx + self.BUBBLE_PAD_X, by + self.BUBBLE_PAD_Y,
                      text=display, font=self.BUBBLE_FONT,
                      fill=self.BUBBLE_FG, anchor="nw", tags=("bubble",))

        delay = int(self.BUBBLE_SHOW_DURATION * 1000)
        self.bubble_job = self.root.after(delay, self._hide_bubble)

    def _hide_bubble(self):
        """隐藏气泡"""
        self.canvas.delete("bubble")
        if self.bubble_job:
            self.root.after_cancel(self.bubble_job)
            self.bubble_job = None

    def _rounded_rect_poly(self, x1, y1, x2, y2, r):
        """生成圆角矩形的多边形顶点"""
        pts = []
        n = 10
        cx, cy = x2 - r, y1 + r
        for i in range(n + 1):
            a = -90 + (i / n) * 90
            rad = a * _m.pi / 180
            pts.append((cx + r * _cos(rad), cy + r * _sin(rad)))
        cx, cy = x2 - r, y2 - r
        for i in range(n + 1):
            a = (i / n) * 90
            rad = a * _m.pi / 180
            pts.append((cx + r * _cos(rad), cy + r * _sin(rad)))
        cx, cy = x1 + r, y2 - r
        for i in range(n + 1):
            a = 90 + (i / n) * 90
            rad = a * _m.pi / 180
            pts.append((cx + r * _cos(rad), cy + r * _sin(rad)))
        cx, cy = x1 + r, y1 + r
        for i in range(n + 1):
            a = 180 + (i / n) * 90
            rad = a * _m.pi / 180
            pts.append((cx + r * _cos(rad), cy + r * _sin(rad)))
        flat = []
        for p in pts:
            flat.extend([round(p[0], 1), round(p[1], 1)])
        return flat

    # ======================== 状态切换 ========================

    def set_state(self, new_state):
        """切换到新状态"""
        if new_state not in self.photo_images:
            return
        old_state = self.current_state
        self.current_state = new_state

        # 更新图片
        img = self.photo_images[new_state]
        self.canvas.itemconfig(self.img_on_canvas, image=img)
        # 图像尺寸可能变化，重新定位到底部
        cx = (self.win_size - img.width()) // 2
        cy = self.win_size - img.height() - 8
        self.canvas.coords(self.img_on_canvas, cx, cy)
        # 让窗口自动适配内容尺寸
        self.root.update_idletasks()

        # 显示对应气泡
        self._show_bubble(self.STATE_LABELS[new_state])

        # 状态进入逻辑
        now = time.time()
        if new_state == self.HOMEWORK:
            self.homework_start_time = now
            self.interrupt_start_time = None
        elif new_state in (self.HOMEWORK_INTERRUPTED, self.SLEEPING_INTERRUPTED):
            self.interrupt_start_time = now

    def on_mouse_down(self, event):
        """鼠标按下：记录偏移量 + 触发点击逻辑"""
        self.offset_x = event.x
        self.offset_y = event.y
        self._handle_click(event)

    def _handle_click(self, event):
        """点击状态切换逻辑"""
        if self.current_state == self.HOMEWORK:
            self.set_state(self.HOMEWORK_INTERRUPTED)
        elif self.current_state == self.SLEEPING:
            self.set_state(self.SLEEPING_INTERRUPTED)
        # 其他状态点击无效（set_state 已自动显示气泡）

    def on_drag(self, event):
        """拖拽事件"""
        x = self.root.winfo_x() + event.x - self.offset_x
        y = self.root.winfo_y() + event.y - self.offset_y
        self.root.geometry(f"+{x}+{y}")

    def show_context_menu(self, event):
        """右键菜单"""
        menu = tk.Menu(self.root, tearoff=0, bg="#333", fg="white",
                        activebackground="#555", activeforeground="white",
                        font=("Microsoft YaHei", 10))
        menu.add_command(label="🌐 翻译", command=self.open_translate_window)
        menu.add_separator()
        menu.add_command(label="退出", command=self.root.quit)
        try:
            menu.tk_popup(self.root.winfo_x() + event.x,
                          self.root.winfo_y() + event.y)
        finally:
            menu.grab_release()

    # ======================== 翻译折叠面板 ========================

    def _apply_win_size(self):
        """根据当前展开状态设置窗口尺寸"""
        w = self.win_size
        h = self.win_size + self.TOGGLE_BAR_H
        if self.PANEL_EXPANDED:
            h += self.PANEL_H
        self.root.geometry(f"{w}x{h}")

    def toggle_panel(self, event=None):
        """展开 / 折叠翻译面板"""
        if self.PANEL_EXPANDED:
            self.translate_panel.pack_forget()
            self.PANEL_EXPANDED = False
            self.toggle_icon.config(text="▲  展开翻译")
        else:
            self.translate_panel.pack(side=tk.TOP, fill=tk.X, before=self.toggle_bar)
            self.PANEL_EXPANDED = True
            self.toggle_icon.config(text="▼  收起翻译")
            # 展开后生成圆角按钮
            self._build_panel_btn()
        self._apply_win_size()

    # ======================== 翻译窗口 + API（单行输入，小巧窗口）=======================

    def open_translate_window(self):
        """打开翻译窗口（单行输入，Enter 翻译）"""
        if hasattr(self, '_trans_win') and self._trans_win is not None:
            try:
                self._trans_win.lift()
                self._trans_win.focus()
                return
            except tk.TclError:
                pass

        win = tk.Toplevel(self.root)
        win.title("翻译")
        win.resizable(False, False)  # 禁止用户拉伸
        win.configure(bg="#F0F2F5")
        win.attributes("-topmost", True)
        self._trans_win = win
        self._translating = False

        # 窗口位置
        ww0, wh0 = 380, 190
        self.root.update_idletasks()
        mx = self.root.winfo_x()
        my = self.root.winfo_y()
        mw = self.root.winfo_width()
        mh = self.root.winfo_height()
        win.geometry(f"{ww0}x{wh0}+{mx + mw - ww0}+{my + mh + 4}")
        self._win_w = ww0  # 保存用于后续计算

        def _on_close():
            self._trans_win = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", _on_close)

        # ---- 主体 ----
        content = tk.Frame(win, bg="#F0F2F5", padx=16, pady=14)
        content.pack(fill=tk.BOTH, expand=True)

        # ---- 输入（白色浅边框）----
        tk.Label(content, text="输入", bg="#F0F2F5",
                 fg="#888888", font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W, pady=(0, 4))

        input_frame = tk.Frame(content, bg="white",
                                highlightbackground="#D8D8D8", highlightthickness=1)
        input_frame.pack(fill=tk.X, pady=(0, 10))

        self.src_entry = tk.Entry(input_frame, font=("Microsoft YaHei UI", 11),
                                   relief=tk.FLAT, borderwidth=0,
                                   bg="white", fg="#333333",
                                   insertbackground="#4A90D9",
                                   highlightthickness=0)
        self.src_entry.pack(fill=tk.X, ipadx=8, ipady=6)
        self.src_entry.bind("<Return>", lambda e: (self.do_translate(), "break")[1])

        # ---- 结果（多行 Text，自动换行，自适应高度）----
        tk.Label(content, text="翻译结果", bg="#F0F2F5",
                 fg="#888888", font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W, pady=(0, 4))

        result_frame = tk.Frame(content, bg="white",
                                 highlightbackground="#D8D8D8", highlightthickness=1)
        result_frame.pack(fill=tk.X)

        self.dst_text = tk.Text(result_frame, font=("Microsoft YaHei UI", 11),
                                 relief=tk.FLAT, borderwidth=0,
                                 wrap=tk.WORD,           # 自动换行
                                 padx=10, pady=8,
                                 bg="white", fg="#333333",
                                 height=2,
                                 highlightthickness=0)
        self.dst_text.pack(fill=tk.X)

        # 复制按钮
        copy_btn = tk.Button(content, text="📋 复制",
                              bg="#E8E8E8", fg="#888888",
                              activebackground="#D5D5D5",
                              activeforeground="#555555",
                              font=("Microsoft YaHei UI", 9),
                              relief=tk.FLAT, cursor="hand2",
                              padx=8, pady=0,
                              command=self._copy_result)
        copy_btn.pack(anchor=tk.E, pady=(6, 0))

        self.src_entry.focus_set()

    # ---- 工具：根据文本行数调整结果框高度 ----
    def _adjust_result_height(self, text):
        """让 dst_text 和窗口自动适配文本行数"""
        try:
            win = self._trans_win
            t = self.dst_text
            # 估算行数：取字符数 / 每行大约字符数 + 换行符数量
            cw = t.winfo_width()
            if cw < 30:
                cw = 340  # fallback
            # 中文字符约占 2 个宽度单位，英文 1 个
            en_chars = sum(1 for ch in text if ord(ch) < 256)
            zh_chars = len(text) - en_chars
            avg_chars_per_line = max(1, cw // 12)  # 约 12px/字
            lines = (zh_chars * 2 + en_chars) // avg_chars_per_line + text.count('\n') + 1
            lines = max(2, min(lines, 8))  # 2~8 行
            t.config(height=lines)
            win.update_idletasks()
            # 重新调整窗口高度（固定宽度）
            want_h = win.winfo_reqheight()
            win.geometry(f"{self._win_w}x{want_h}")
        except (tk.TclError, AttributeError):
            pass

    def do_translate(self):
        """触发翻译（后台线程，固定翻译为中文）"""
        if self._translating:
            return
        text = self.src_entry.get().strip()
        if not text:
            return
        self._translating = True
        self._show_status("翻译中…")
        t = threading.Thread(target=self._translate_thread,
                             args=(text, "zh-CN"), daemon=True)
        t.start()

    def _show_status(self, msg):
        """在结果区显示状态信息"""
        try:
            self.dst_text.delete("1.0", tk.END)
            self.dst_text.insert("1.0", msg)
        except tk.TclError:
            pass

    @staticmethod
    def _detect_lang(text):
        """基于 Unicode 范围做简单语言检测"""
        kana = hangul = cyrillic = cjk = 0
        for ch in text[:300]:
            cp = ord(ch)
            if 0x3040 <= cp <= 0x309F or 0x30A0 <= cp <= 0x30FF:
                kana += 1; cjk += 1
            elif 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF:
                cjk += 1
            elif 0xAC00 <= cp <= 0xD7AF:
                hangul += 1; cjk += 1
            elif 0x0400 <= cp <= 0x04FF:
                cyrillic += 1
        if kana > 0: return "ja"
        if hangul > len(text[:300]) * 0.3: return "ko"
        if cyrillic > len(text[:300]) * 0.3: return "ru"
        if cjk > 0: return "zh-CN"
        return "en"

    def _translate_thread(self, text, target):
        """后台翻译线程 — 多个 API 并行抢答，谁快用谁"""
        source = self._detect_lang(text)
        result = [None]       # list wrapper 供闭包写
        done = threading.Event()

        def _mymemory():
            if not HAS_REQUESTS:
                return
            try:
                url = "https://api.mymemory.translated.net/get"
                r = requests.get(url, params={"q": text, "langpair": f"{source}|{target}"},
                                 timeout=5)
                d = r.json()
                if d.get("responseStatus") == 200:
                    t = d["responseData"]["translatedText"]
                    if t and t.strip() and not done.is_set():
                        result[0] = t.strip()
                        done.set()
            except Exception:
                pass

        def _google():
            try:
                url = "https://translate.googleapis.com/translate_a/single"
                params = {"client": "gtx", "sl": "auto", "tl": target, "dt": "t", "q": text}
                if HAS_REQUESTS:
                    resp = requests.get(url, params=params, timeout=5)
                    data = resp.json()
                else:
                    qs = urllib.parse.urlencode(params)
                    with urllib.request.urlopen(f"{url}?{qs}", timeout=5) as f:
                        data = json.loads(f.read().decode())
                if isinstance(data, list) and len(data) > 0:
                    parts = [item[0] for item in data[0]
                             if isinstance(item, list) and len(item) > 0 and item[0]]
                    if parts and not done.is_set():
                        result[0] = "".join(parts)
                        done.set()
            except Exception:
                pass

        def _libre():
            """LibreTranslate 公共实例"""
            payload = json.dumps({"q": text, "source": "auto", "target": target}).encode()
            for host in ("https://libretranslate.com", "https://translate.argosopentech.com"):
                if done.is_set():
                    return
                try:
                    if HAS_REQUESTS:
                        r = requests.post(host + "/translate", data=payload,
                                          headers={"Content-Type": "application/json"}, timeout=4)
                        d = r.json()
                        if d.get("translatedText") and not done.is_set():
                            result[0] = d["translatedText"]
                            done.set()
                    else:
                        qs = urllib.parse.urlencode({"q": text, "source": "auto", "target": target})
                        with urllib.request.urlopen(host + "/translate?" + qs, timeout=4) as f:
                            d = json.loads(f.read().decode())
                            if d.get("translatedText") and not done.is_set():
                                result[0] = d["translatedText"]
                                done.set()
                except Exception:
                    continue

        # ---- 同时启动所有源，谁快用谁 ----
        runners = [threading.Thread(target=_google, daemon=True)]
        if HAS_REQUESTS:
            runners.append(threading.Thread(target=_mymemory, daemon=True))
            runners.append(threading.Thread(target=_libre, daemon=True))
        for t in runners:
            t.start()

        done.wait(timeout=6)

        # ---- 非英文拉丁语补尝（MyMemory 不识别时换源） ----
        if result[0] and source == "en" and result[0].strip().lower() == text.strip().lower():
            result[0] = None
            for alt_src in ("fr", "es", "de", "it", "pt", "nl", "id"):
                if done.is_set():
                    break
                try:
                    url = "https://api.mymemory.translated.net/get"
                    r = requests.get(url, params={"q": text, "langpair": f"{alt_src}|{target}"}, timeout=4)
                    d = r.json()
                    if d.get("responseStatus") == 200:
                        t = d["responseData"]["translatedText"]
                        if t and t.strip() and t.strip().lower() != text.strip().lower():
                            result[0] = t.strip()
                            break
                except Exception:
                    continue

        self.root.after(0, self._finish_translate, result[0])

    def _finish_translate(self, result):
        """翻译完成，更新 UI"""
        self._translating = False
        try:
            if result:
                self.dst_text.delete("1.0", tk.END)
                self.dst_text.insert("1.0", result)
                self._adjust_result_height(result)
            else:
                self._show_status("翻译失败，请检查网络后重试")
        except tk.TclError:
            pass

    def _copy_result(self):
        """复制翻译结果到剪贴板"""
        try:
            text = self.dst_text.get("1.0", tk.END).strip()
            if text:
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
                orig = text
                self._show_status("✅ 已复制到剪贴板")
                self.root.after(1500, lambda: self._show_status(orig))
        except tk.TclError:
            pass

    # ======================== 主循环 ========================

    def update(self):
        """定时检查状态转换"""
        now = time.time()

        if self.current_state == self.HOMEWORK:
            # 肝作业持续超过阈值 → 睡觉
            if now - self.homework_start_time >= self.HOMEWORK_TO_SLEEP_DELAY:
                self.set_state(self.SLEEPING)

        elif self.current_state == self.HOMEWORK_INTERRUPTED:
            # 被打扰5秒后恢复肝作业
            if self.interrupt_start_time and now - self.interrupt_start_time >= self.INTERRUPT_DURATION:
                self.set_state(self.HOMEWORK)

        elif self.current_state == self.SLEEPING_INTERRUPTED:
            # 睡觉被打扰5秒后开始肝作业
            if self.interrupt_start_time and now - self.interrupt_start_time >= self.INTERRUPT_DURATION:
                self.set_state(self.HOMEWORK)

        # 每 500ms 检查一次
        self.root.after(500, self.update)

    def run(self):
        """启动程序"""
        # 设置窗口大小（含折叠条）
        self._apply_win_size()
        # 设置初始位置（屏幕右上角附近）
        screen_w = self.root.winfo_screenwidth()
        x = screen_w - self.win_size - 50
        y = 50
        self.root.geometry(f"+{x}+{y}")
        self.root.mainloop()


def main():
    root = tk.Tk()
    pet = DeskPet(root)
    pet.run()


if __name__ == "__main__":
    main()
