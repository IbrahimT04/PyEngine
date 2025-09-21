# game_full_ui.py
"""
Full-featured modern OpenGL UI:
 - Keyboard navigation (arrows, Tab, Enter)
 - Gamepad navigation (first joystick): left stick/dpad + button 0
 - Glyph atlas (Pillow) and efficient text rendering
 - Transitions: fade and slide for overlays
 - Home screen, Menu, Options, Pause menu, Playing HUD
 - Modern OpenGL (VAO/VBO + GLSL)

Requirements:
    pip install glfw PyOpenGL Pillow numpy
"""
import glfw
import time
import math
import ctypes
import numpy as np
from dataclasses import dataclass
from typing import Tuple, Dict, List, Optional

# Try Pillow for atlas creation
USE_PIL = True
try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    USE_PIL = False

from OpenGL.GL import *

# ---------- Utility: easing ----------
def lerp(a, b, t): return a + (b - a) * t
def clamp(x, a, b): return max(a, min(b, x))
def smoothstep(x): return x * x * (3 - 2 * x)
def ease_out_cubic(x): return 1 - pow(1 - x, 3)

# ---------- Shaders ----------
VERT_TRI = """
#version 330 core
layout(location=0) in vec3 a_pos;
layout(location=1) in vec3 a_col;
uniform mat4 u_model;
uniform mat4 u_vp;
out vec3 v_col;
void main() {
    v_col = a_col;
    gl_Position = u_vp * u_model * vec4(a_pos, 1.0);
}
"""
FRAG_TRI = """
#version 330 core
in vec3 v_col;
out vec4 o_color;
void main(){ o_color = vec4(v_col, 1.0); }
"""

VERT_UI = """
#version 330 core
layout(location=0) in vec2 a_pos;
layout(location=1) in vec2 a_uv;
layout(location=2) in float a_alpha; // per-vertex alpha for smooth fade
out vec2 v_uv;
out float v_alpha;
uniform mat4 u_proj;
void main(){
    v_uv = a_uv;
    v_alpha = a_alpha;
    gl_Position = u_proj * vec4(a_pos, 0.0, 1.0);
}
"""
FRAG_UI = """
#version 330 core
in vec2 v_uv;
in float v_alpha;
uniform sampler2D u_tex;
uniform vec4 u_color;
out vec4 o_color;
void main(){
    vec4 t = texture(u_tex, v_uv);
    // multiply color * texture alpha and per-vertex alpha
    vec4 col = vec4(u_color.rgb, u_color.a * t.a * v_alpha);
    o_color = col * t;
}
"""

def compile_program(vs_src: bytes, fs_src: bytes) -> int:
    vs = glCreateShader(GL_VERTEX_SHADER)
    glShaderSource(vs, vs_src)
    glCompileShader(vs)
    if not glGetShaderiv(vs, GL_COMPILE_STATUS):
        raise RuntimeError(glGetShaderInfoLog(vs))

    fs = glCreateShader(GL_FRAGMENT_SHADER)
    glShaderSource(fs, fs_src)
    glCompileShader(fs)
    if not glGetShaderiv(fs, GL_COMPILE_STATUS):
        raise RuntimeError(glGetShaderInfoLog(fs))

    prog = glCreateProgram()
    glAttachShader(prog, vs)
    glAttachShader(prog, fs)
    glLinkProgram(prog)
    if not glGetProgramiv(prog, GL_LINK_STATUS):
        raise RuntimeError(glGetProgramInfoLog(prog))

    glDeleteShader(vs); glDeleteShader(fs)
    return prog

# ---------- Glyph atlas and text rendering ----------
class GlyphAtlas:
    def __init__(self, font_path: Optional[str] = None, font_size: int = 24, padding: int = 2, chars: str = None):
        self.font_size = font_size
        self.padding = padding
        self.chars = chars if chars is not None else ''.join(chr(i) for i in range(32,127))
        self.glyphs = {}  # char -> (x,y,w,h,advance,ox,oy)
        self.tex = 0
        self.tex_w = 0; self.tex_h = 0
        if USE_PIL:
            try:
                if font_path:
                    self.font = ImageFont.truetype(font_path, font_size)
                else:
                    # try common fallback
                    self.font = ImageFont.truetype("DejaVuSans.ttf", font_size)
            except Exception:
                try:
                    self.font = ImageFont.load_default()
                except Exception:
                    self.font = None
            if self.font is None:
                # cannot create atlas without font
                print("GlyphAtlas: Pillow font load failed; text rendering disabled.")
                return
            self._build_atlas()
        else:
            print("GlyphAtlas: Pillow not available — text disabled.")

    def _build_atlas(self):
        # measure glyph sizes
        glyph_images = []
        total_w = 0
        max_h = 0
        # gather bitmaps
        for ch in self.chars:
            # measure
            mask = self.font.getmask(ch, mode="L")
            w, h = mask.size
            # If width/height zero, render a single pixel to avoid zero width
            if w == 0: w = self.font_size // 4
            if h == 0: h = self.font_size // 2
            # create image and draw char onto it with alpha
            img = Image.new("RGBA", (w + self.padding*2, h + self.padding*2), (0,0,0,0))
            d = ImageDraw.Draw(img)
            d.text((self.padding, self.padding), ch, font=self.font, fill=(255,255,255,255))
            glyph_images.append((ch, img))
            total_w += img.width
            max_h = max(max_h, img.height)

        # pack into rows: simple packing into one row until width > limit, then new row
        # choose width limit as min(total_w, 2048)
        max_tex_w = min(total_w, 2048)
        x = 0; y = 0; row_h = 0
        placements = []
        atlas_w = max_tex_w
        atlas_h = 0
        for ch, img in glyph_images:
            w, h = img.size
            if x + w > atlas_w:
                # next row
                x = 0
                y += row_h
                atlas_h += row_h
                row_h = 0
            placements.append((ch, x, y, img))
            x += w
            row_h = max(row_h, h)
        atlas_h += row_h
        # pad to power-of-two optionally (not required)
        # create atlas image
        atlas = Image.new("RGBA", (atlas_w, atlas_h), (0,0,0,0))
        for ch, px, py, img in placements:
            atlas.paste(img, (px, py), img)
            self.glyphs[ch] = (px, py, img.width, img.height)
        # upload atlas to GL texture
        atlas_data = atlas.tobytes("raw", "RGBA")
        self.tex_w, self.tex_h = atlas.size
        self.tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self.tex)
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, self.tex_w, self.tex_h, 0, GL_RGBA, GL_UNSIGNED_BYTE, atlas_data)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glBindTexture(GL_TEXTURE_2D, 0)
        print(f"GlyphAtlas: built texture {self.tex_w}x{self.tex_h} with {len(self.glyphs)} glyphs")

    def get_glyph(self, ch):
        return self.glyphs.get(ch, None)

class TextRenderer:
    def __init__(self, atlas: GlyphAtlas):
        self.atlas = atlas
        # dynamic VBO for text quads: pos.xy, uv.xy, alpha
        self.vbo = glGenBuffers(1)
        self.vao = glGenVertexArrays(1)
        glBindVertexArray(self.vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        # reserve some initial space
        glBufferData(GL_ARRAY_BUFFER, 1024 * ctypes.sizeof(ctypes.c_float), None, GL_DYNAMIC_DRAW)
        # layout: pos.x,pos.y (float2) | uv.x,uv.y (float2) | alpha (float)
        stride = (2 + 2 + 1) * ctypes.sizeof(ctypes.c_float)
        glEnableVertexAttribArray(0)  # pos
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(0))
        glEnableVertexAttribArray(1)  # uv
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(2 * ctypes.sizeof(ctypes.c_float)))
        glEnableVertexAttribArray(2)  # alpha
        glVertexAttribPointer(2, 1, GL_FLOAT, GL_FALSE, stride, ctypes.c_void_p(4 * ctypes.sizeof(ctypes.c_float)))
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glBindVertexArray(0)

    def draw_text(self, prog, text: str, left_ndc: float, top_ndc: float, color=(1,1,1,1), alpha=1.0):
        """Emit quads and draw. left_ndc, top_ndc are NDC coords where top-left of text will be."""
        if not USE_PIL or self.atlas.tex == 0:
            return
        vp = glGetIntegerv(GL_VIEWPORT)
        win_w, win_h = vp[2], vp[3]
        # compute pixel sizes and map to ndc for each glyph
        # build array of vertices for all glyph quads
        verts = []
        pen_x = left_ndc
        pen_y = top_ndc
        for ch in text:
            g = self.atlas.get_glyph(ch)
            if g is None:
                # advance by space approx
                space_px = self.atlas.font_size if self.atlas.font_size else 10
                ndc_advance = (space_px / win_w) * 2.0
                pen_x += ndc_advance
                continue
            gx, gy, gw, gh = g
            ndc_w = (gw / win_w) * 2.0
            ndc_h = (gh / win_h) * 2.0
            left = pen_x
            right = pen_x + ndc_w
            top = pen_y
            bottom = pen_y - ndc_h
            uv_left = gx / self.atlas.tex_w
            uv_top = gy / self.atlas.tex_h
            uv_right = (gx + gw) / self.atlas.tex_w
            uv_bottom = (gy + gh) / self.atlas.tex_h
            # two triangles
            # tri1
            verts += [left, bottom, uv_left, uv_bottom, alpha]
            verts += [right, bottom, uv_right, uv_bottom, alpha]
            verts += [right, top, uv_right, uv_top, alpha]
            # tri2
            verts += [left, bottom, uv_left, uv_bottom, alpha]
            verts += [right, top, uv_right, uv_top, alpha]
            verts += [left, top, uv_left, uv_top, alpha]
            pen_x += ndc_w  # simple horizontal advance
        if len(verts) == 0:
            return
        arr = np.array(verts, dtype=np.float32)
        glUseProgram(prog)
        glUniform4f(glGetUniformLocation(prog, "u_color"), *color)
        # bind atlas
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self.atlas.tex)
        glUniform1i(glGetUniformLocation(prog, "u_tex"), 0)
        glBindVertexArray(self.vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo)
        glBufferData(GL_ARRAY_BUFFER, arr.nbytes, arr, GL_DYNAMIC_DRAW)
        glDrawArrays(GL_TRIANGLES, 0, int(len(arr) / 5))
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glBindVertexArray(0)
        glBindTexture(GL_TEXTURE_2D, 0)
        glUseProgram(0)

# ---------- Focusable UI dataclasses ----------
@dataclass
class FocusableButton:
    cx: float; cy: float; w: float; h: float; label: str; action: callable
    hover: bool = False
    focused: bool = False
    visible: bool = True
    enabled: bool = True
    def contains(self, nx, ny): return (self.cx - self.w/2 <= nx <= self.cx + self.w/2 and self.cy - self.h/2 <= ny <= self.cy + self.h/2)

@dataclass
class FocusableSlider:
    cx: float; cy: float; w: float; h: float; minv: float; maxv: float; value: float; label: str
    dragging: bool = False
    focused: bool = False
    visible: bool = True
    enabled: bool = True
    def normalized(self): return (self.value - self.minv) / (self.maxv - self.minv)
    def set_from_norm(self, t): self.value = self.minv + clamp(t, 0.0, 1.0) * (self.maxv - self.minv)
    def contains(self, nx, ny): return (self.cx - self.w/2 <= nx <= self.cx + self.w/2 and self.cy - self.h/2 <= ny <= self.cy + self.h/2)

# ---------- Main window class ----------
class GameFullUI:
    def __init__(self, w=1280, h=720, title="Full UI Game"):
        if not glfw.init():
            raise RuntimeError("glfw.init failed")
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        self.w, self.h = w, h
        self.win = glfw.create_window(w, h, title, None, None)
        if not self.win:
            glfw.terminate(); raise RuntimeError("Failed to create window")
        glfw.set_window_pos(self.win, 200, 120)
        glfw.make_context_current(self.win)
        glfw.swap_interval(1)
        # programs
        self.prog_tri = compile_program(VERT_TRI, FRAG_TRI)
        self.prog_ui = compile_program(VERT_UI, FRAG_UI)
        # triangle VAO/VBO
        tri_data = np.array([
            -0.5,-0.5,0.0,  1.0,0.0,0.0,
             0.5,-0.5,0.0,  0.0,1.0,0.0], dtype=np.float32)  # placeholder; will set correctly
        # easier: create tri arrays
        tri_data = np.array([
            -0.5, -0.5, 0.0,  1.0,0.0,0.0,
             0.5, -0.5, 0.0,  0.0,1.0,0.0,
             0.0,  0.5, 0.0,  0.0,0.0,1.0,
        ], dtype=np.float32)
        self.tri_vao = glGenVertexArrays(1)
        self.tri_vbo = glGenBuffers(1)
        glBindVertexArray(self.tri_vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.tri_vbo)
        glBufferData(GL_ARRAY_BUFFER, tri_data.nbytes, tri_data, GL_STATIC_DRAW)
        stride = 6 * ctypes.sizeof(ctypes.c_float)
        glEnableVertexAttribArray(0); glVertexAttribPointer(0,3,GL_FLOAT,GL_FALSE,stride,ctypes.c_void_p(0))
        glEnableVertexAttribArray(1); glVertexAttribPointer(1,3,GL_FLOAT,GL_FALSE,stride,ctypes.c_void_p(3*ctypes.sizeof(ctypes.c_float)))
        glBindBuffer(GL_ARRAY_BUFFER, 0); glBindVertexArray(0)
        # UI VAO/VBO for colored rectangles (pos.xy, uv.xy, alpha)
        GameFullUI.ui_vao = glGenVertexArrays(1)
        GameFullUI.ui_vbo = glGenBuffers(1)
        glBindVertexArray(GameFullUI.ui_vao)
        glBindBuffer(GL_ARRAY_BUFFER, GameFullUI.ui_vbo)
        glBufferData(GL_ARRAY_BUFFER, 4096, None, GL_DYNAMIC_DRAW)
        # layout: pos.xy (2), uv.xy (2), alpha (1) -- total 5 floats
        glEnableVertexAttribArray(0); glVertexAttribPointer(0,2,GL_FLOAT,GL_FALSE,5*ctypes.sizeof(ctypes.c_float),ctypes.c_void_p(0))
        glEnableVertexAttribArray(1); glVertexAttribPointer(1,2,GL_FLOAT,GL_FALSE,5*ctypes.sizeof(ctypes.c_float),ctypes.c_void_p(2*ctypes.sizeof(ctypes.c_float)))
        glEnableVertexAttribArray(2); glVertexAttribPointer(2,1,GL_FLOAT,GL_FALSE,5*ctypes.sizeof(ctypes.c_float),ctypes.c_void_p(4*ctypes.sizeof(ctypes.c_float)))
        glBindBuffer(GL_ARRAY_BUFFER, 0); glBindVertexArray(0)
        # glyph atlas & text renderer
        self.atlas = GlyphAtlas(font_size=24) if USE_PIL else GlyphAtlas(None)  # will print if PIL missing
        self.text_renderer = TextRenderer(self.atlas) if (USE_PIL and self.atlas.tex != 0) else None
        # UI controls
        self.home_buttons: List[FocusableButton] = []
        self.menu_buttons: List[FocusableButton] = []
        self.pause_buttons: List[FocusableButton] = []
        self.options_sliders: List[FocusableSlider] = []
        # construct controls with actions that modify state below
        # values for triangle
        self.tri_scale = 1.0
        self.tri_speed = 1.0
        # create focusable controls using wrapper dataclasses mapping to rendering coordinates
        # Home/Menu: Start, Options, Quit (same coords)
        start_btn = FocusableButton(0.0, 0.28, 1.0, 0.24, "Start", action=lambda: self.start_game())
        options_btn = FocusableButton(0.0, -0.02, 1.0, 0.24, "Options", action=lambda: self.toggle_options())
        quit_btn = FocusableButton(0.0, -0.36, 1.0, 0.24, "Quit", action=lambda: self.quit_game())
        self.home_buttons = [start_btn, options_btn, quit_btn]
        self.menu_buttons = [start_btn, options_btn, quit_btn]
        # pause menu centered buttons
        resume_btn = FocusableButton(0.0, 0.18, 0.6, 0.18, "Resume", action=lambda: self.resume_from_pause())
        p_options_btn = FocusableButton(0.0, -0.02, 0.6, 0.18, "Options", action=lambda: self.toggle_options())
        main_btn = FocusableButton(0.0, -0.22, 0.6, 0.18, "Main Menu", action=lambda: self.goto_menu())
        p_quit_btn = FocusableButton(0.0, -0.42, 0.6, 0.18, "Quit", action=lambda: self.quit_game())
        self.pause_buttons = [resume_btn, p_options_btn, main_btn, p_quit_btn]
        # options sliders
        s_scale = FocusableSlider(0.0, 0.10, 0.7, 0.10, 0.2, 3.0, 1.0, label="Triangle scale")
        s_speed = FocusableSlider(0.0, -0.10, 0.7, 0.10, 0.1, 3.0, 1.0, label="Triangle speed")
        self.options_sliders = [s_scale, s_speed]
        # focus system
        self.focus_list: List = []  # built each frame
        self.focus_index = 0
        self.focus_time_last = 0.0
        # navigation repeat timers
        self.nav_repeat_delay = 0.25
        self.nav_last = 0.0
        # gamepad state
        self.joy_present = False
        self.joy_id = None
        self.joy_deadzone = 0.5
        self.gamepad_nav_last = 0.0
        self.gamepad_nav_repeat = 0.25
        self.prev_axis = (0.0, 0.0)
        # scenes & transitions
        self.scene = "home"  # home/menu/playing
        self.show_options = False
        self.paused = False
        self.pause_menu_open = False
        # transition values
        self.menu_alpha = 0.0
        self.home_alpha = 0.0
        self.pause_alpha = 0.0
        self.options_slide = -0.6  # y offset when hidden, slides to 0
        # timing for FPS
        self.last_time = time.time()
        self.fps = 0.0; self.frame_count = 0; self.fps_last = time.time()
        # callbacks
        glfw.set_mouse_button_callback(self.win, self.on_mouse)
        glfw.set_key_callback(self.win, self.on_key)
        glfw.set_window_size_callback(self.win, self.on_resize)
        glClearColor(0.06, 0.08, 0.10, 1.0)
        glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        print("Full UI running. Keyboard: arrows/tab/enter; P pause; O options; Gamepad supported (first joystick).")

    # ---------- actions ----------
    def start_game(self):
        self.scene = "playing"
        self.paused = False
        self.pause_menu_open = False

    def quit_game(self):
        glfw.set_window_should_close(self.win, True)

    def goto_menu(self):
        self.scene = "menu"
        self.show_options = False
        self.paused = False
        self.pause_menu_open = False

    def resume_from_pause(self):
        self.paused = False
        self.pause_menu_open = False

    def toggle_options(self):
        self.show_options = not self.show_options

    # ---------- input handlers ----------
    def on_resize(self, wdw, width, height):
        self.w, self.h = width, height
        glViewport(0, 0, width, height)

    def window_coords_to_ndc(self, mx, my):
        nx = (mx / self.w) * 2.0 - 1.0
        ny = -((my / self.h) * 2.0 - 1.0)
        return nx, ny

    def on_mouse(self, wdw, button, action, mods):
        if button != glfw.MOUSE_BUTTON_LEFT: return
        mx, my = glfw.get_cursor_pos(self.win)
        nx, ny = self.window_coords_to_ndc(mx, my)
        # try click activation on visible controls
        if self.scene in ("home","menu"):
            btns = self.home_buttons if self.scene=="home" else self.menu_buttons
            # if options visible then prefer sliders
            if self.show_options:
                for s in self.options_sliders:
                    if s.contains(nx, ny):
                        s.dragging = True; s.focused = True
                        self.focus_list = [s]; self.focus_index = 0
                        return
            else:
                for i, b in enumerate(btns):
                    if b.contains(nx, ny):
                        b.action(); return
        elif self.scene == "playing":
            # top-left pause box and menu box
            pause_box = (-0.9, 0.85, 0.12, 0.08)
            menu_box = (-0.74, 0.85, 0.22, 0.08)
            # simple checks
            px, py, pw, ph = pause_box; if_pause = (px - pw/2 <= nx <= px+pw/2 and py-ph/2 <= ny <= py+ph/2)
            mx_box = (-0.74,0.85,0.22,0.08)
            # If pause open, route to pause menu buttons intersection
            if self.pause_menu_open:
                for b in self.pause_buttons:
                    if b.contains(nx, ny):
                        b.action(); return
            # otherwise if clicked pause icon, open pause
            if if_pause:
                self.paused = True; self.pause_menu_open = True
                return

    def on_key(self, wdw, key, scancode, action, mods):
        if action != glfw.PRESS: return
        # global keys
        if key == glfw.KEY_ESCAPE:
            if self.scene == "playing":
                # toggle pause menu
                self.paused = not self.paused
                self.pause_menu_open = self.paused
            else:
                glfw.set_window_should_close(self.win, True)
        elif key in (glfw.KEY_ENTER, glfw.KEY_KP_ENTER):
            # activate currently focused
            self.activate_focused()
        elif key == glfw.KEY_TAB:
            # move focus forward
            self.move_focus(1)
        elif key == glfw.KEY_UP:
            self.move_focus(-1)
        elif key == glfw.KEY_DOWN:
            self.move_focus(1)
        elif key == glfw.KEY_LEFT:
            # for sliders reduce value
            self.adjust_slider(-0.02)
        elif key == glfw.KEY_RIGHT:
            self.adjust_slider(0.02)
        elif key == glfw.KEY_O:
            self.toggle_options()
        elif key == glfw.KEY_P:
            if self.scene == "playing":
                self.paused = not self.paused
                self.pause_menu_open = self.paused
        elif key == glfw.KEY_Q:
            glfw.set_window_should_close(self.win, True)

    # ---------- focus & navigation ----------
    def build_focus_list(self):
        # builds current visible focusable controls in render order
        lst = []
        if self.scene == "home":
            if self.show_options:
                lst.extend(self.options_sliders)
            else:
                lst.extend(self.home_buttons)
        elif self.scene == "menu":
            if self.show_options:
                lst.extend(self.options_sliders)
            else:
                lst.extend(self.menu_buttons)
        elif self.scene == "playing":
            if self.pause_menu_open:
                if self.show_options:
                    lst.extend(self.options_sliders)
                else:
                    lst.extend(self.pause_buttons)
            else:
                # HUD buttons small — add them for navigation
                # create lightweight focusable for pause & main menu HUD
                lst.append(FocusableButton(-0.9,0.85,0.12,0.08,"Pause", action=lambda: self._open_pause()))
                lst.append(FocusableButton(-0.74,0.85,0.22,0.08,"MainMenu", action=lambda: self.goto_menu()))
        # copy into self.focus_list
        self.focus_list = lst
        if len(self.focus_list) == 0:
            self.focus_index = -1
        else:
            # clamp index
            self.focus_index = clamp(self.focus_index, 0, len(self.focus_list)-1)

    def _open_pause(self):
        self.paused = True; self.pause_menu_open = True

    def move_focus(self, delta: int):
        self.build_focus_list()
        if not self.focus_list:
            return
        tnow = time.time()
        if tnow - self.nav_last < self.nav_repeat_delay:
            return
        self.nav_last = tnow
        self.focus_index = (self.focus_index + delta) % len(self.focus_list)
        # visually update focused flags
        for i, f in enumerate(self.focus_list):
            if isinstance(f, FocusableButton) or isinstance(f, FocusableSlider):
                f.focused = (i == self.focus_index)

    def activate_focused(self):
        self.build_focus_list()
        if not self.focus_list or self.focus_index < 0:
            return
        f = self.focus_list[self.focus_index]
        if isinstance(f, FocusableButton):
            f.action()
        elif isinstance(f, FocusableSlider):
            # slider activation toggles dragging
            f.dragging = not getattr(f, "dragging", False)

    def adjust_slider(self, delta_norm):
        # adjust currently focused slider if any
        self.build_focus_list()
        if not self.focus_list or self.focus_index < 0:
            return
        f = self.focus_list[self.focus_index]
        if isinstance(f, FocusableSlider):
            # change value by normalized delta
            t = f.normalized() + delta_norm
            f.set_from_norm(t)

    # ---------- gamepad handling ----------
    def poll_gamepad(self):
        # use first present joystick with gamepad mapping if available
        for jid in range(glfw.JOYSTICK_1, glfw.JOYSTICK_LAST + 1):
            if glfw.joystick_present(jid):
                self.joy_present = True; self.joy_id = jid; break
        if not self.joy_present:
            return
        # poll axes & buttons
        axes = glfw.get_joystick_axes(self.joy_id)
        buttons = glfw.get_joystick_buttons(self.joy_id)
        # axes[0], axes[1] left stick; axes[2] maybe right stick; change small deadzone logic
        if axes:
            ax = axes[0] if len(axes) > 0 else 0.0
            ay = axes[1] if len(axes) > 1 else 0.0
            now = time.time()
            # consider navigation if magnitude exceeds deadzone
            if abs(ax) > 0.5 or abs(ay) > 0.5:
                if now - self.gamepad_nav_last > self.gamepad_nav_repeat:
                    # map up/down/left/right from axes
                    if ay < -0.5:
                        self.move_focus(-1)
                    elif ay > 0.5:
                        self.move_focus(1)
                    elif ax < -0.5:
                        # left -> if focused slider, reduce
                        self.adjust_slider(-0.02)
                    elif ax > 0.5:
                        self.adjust_slider(0.02)
                    self.gamepad_nav_last = now
        # button 0 to activate
        if buttons and len(buttons) > 0 and buttons[0] == glfw.PRESS:
            tnow = time.time()
            # simple debouncing
            if tnow - self.nav_last > 0.2:
                self.activate_focused()
                self.nav_last = tnow

    # ---------- rendering helpers ----------
    def tri_model(self, t, scale=1.0):
        tx = math.sin(t) * 0.45; ty = math.cos(t) * 0.25
        s = (abs(math.sin(t))*0.5*scale + 0.3)
        ang = math.sin(t) * math.radians(45.0)
        c = math.cos(ang); sa = math.sin(ang)
        mat = np.array([
            [c*s, -sa*s, 0, 0],
            [sa*s, c*s,  0, 0],
            [0,    0,    1, 0],
            [tx,   ty,   0, 1],
        ], dtype=np.float32)
        return mat

    def draw_rect(self, cx, cy, w, h, color, alpha=1.0):
        left = cx - w/2; right = cx + w/2; top = cy + h/2; bottom = cy - h/2
        quad = np.array([
            left, bottom, 0.0, 1.0, alpha,
            right, bottom, 1.0, 1.0, alpha,
            right, top,    1.0, 0.0, alpha,
            left, bottom, 0.0, 1.0, alpha,
            right, top,    1.0, 0.0, alpha,
            left, top,     0.0, 0.0, alpha,
        ], dtype=np.float32)
        glUseProgram(self.prog_ui)
        # bind white texture (create if needed)
        if not hasattr(self, "white_tex") or self.white_tex == 0:
            pix = bytes([255,255,255,255])
            self.white_tex = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, self.white_tex)
            glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 1,1,0,GL_RGBA,GL_UNSIGNED_BYTE, pix)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
            glBindTexture(GL_TEXTURE_2D, 0)
        glActiveTexture(GL_TEXTURE0)
        glBindTexture(GL_TEXTURE_2D, self.white_tex)
        glUniform1i(glGetUniformLocation(self.prog_ui, "u_tex"), 0)
        glUniform4f(glGetUniformLocation(self.prog_ui, "u_color"), *color)
        glBindVertexArray(GameFullUI.ui_vao)
        glBindBuffer(GL_ARRAY_BUFFER, GameFullUI.ui_vbo)
        glBufferData(GL_ARRAY_BUFFER, quad.nbytes, quad, GL_DYNAMIC_DRAW)
        glDrawArrays(GL_TRIANGLES, 0, 6)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glBindVertexArray(0)
        glBindTexture(GL_TEXTURE_2D, 0)
        glUseProgram(0)

    # ---------- main loop ----------
    def run(self):
        glViewport(0,0,self.w,self.h)
        while not glfw.window_should_close(self.win):
            now = time.time()
            dt = now - self.last_time if self.last_time else 0.0
            self.last_time = now
            self.frame_count += 1
            if now - self.fps_last >= 0.5:
                self.fps = self.frame_count / (now - self.fps_last)
                self.frame_count = 0
                self.fps_last = now

            # poll joystick once
            self.poll_gamepad()
            # build focus list for keyboard/gamepad
            self.build_focus_list()

            # transitions: lerp alphas and slide positions
            target_home = 1.0 if self.scene=="home" else 0.0
            target_menu = 1.0 if (self.scene=="menu") else 0.0
            target_pause = 1.0 if (self.pause_menu_open) else 0.0
            self.home_alpha = lerp(self.home_alpha, target_home, clamp(dt*6.0, 0.0, 1.0))
            self.menu_alpha = lerp(self.menu_alpha, target_menu, clamp(dt*6.0, 0.0, 1.0))
            self.pause_alpha = lerp(self.pause_alpha, target_pause, clamp(dt*8.0, 0.0, 1.0))
            # options slide target 0 if visible else -0.6
            target_slide = 0.0 if self.show_options else -0.6
            self.options_slide = lerp(self.options_slide, target_slide, clamp(dt*8.0, 0.0, 1.0))

            glfw.poll_events()
            # handle dragging for sliders (mouse)
            mx, my = glfw.get_cursor_pos(self.win)
            nx, ny = self.window_coords_to_ndc(mx, my)
            # if mouse pressed state for dragging: check mouse buttons
            mb_left = glfw.get_mouse_button(self.win, glfw.MOUSE_BUTTON_LEFT)
            if mb_left == glfw.PRESS:
                # if options open, update any dragging slider
                for s in self.options_sliders:
                    if s.visible and getattr(s, "dragging", False):
                        left = s.cx - s.w/2; right = s.cx + s.w/2
                        tnorm = (nx - left) / (right - left)
                        s.set_from_norm(tnorm)
            else:
                # release dragging
                for s in self.options_sliders:
                    s.dragging = False

            # clear
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            # draw background triangle (with shader)
            glUseProgram(self.prog_tri)
            t = now
            model = self.tri_model(t, scale=self.options_sliders[0].value if self.options_sliders else 1.0)
            glUniformMatrix4fv(glGetUniformLocation(self.prog_tri, "u_model"), 1, GL_FALSE, model)
            glUniformMatrix4fv(glGetUniformLocation(self.prog_tri, "u_vp"), 1, GL_FALSE, np.eye(4, dtype=np.float32))
            glBindVertexArray(self.tri_vao)
            glDrawArrays(GL_TRIANGLES, 0, 3)
            glBindVertexArray(0)
            glUseProgram(0)

            # Layers based on scene & transitions
            # HOME
            if self.home_alpha > 0.001:
                alpha = self.home_alpha
                # title panel slide slightly from top: implement by shifting y coords using alpha
                title_y = lerp(0.62+0.2, 0.62, smoothstep(alpha))
                # draw title rect
                self.draw_rect(0.0, title_y, 1.6, 0.34, color=(0.02,0.02,0.04,0.7*alpha), alpha=alpha)
                # buttons (Start/Options/Quit)
                for i, b in enumerate(self.home_buttons):
                    hovered = b.contains(nx, ny)
                    col = (0.12, 0.6, 0.2, 0.95*alpha) if i==0 else None
                    if b.label == "Start":
                        self.draw_rect(b.cx, b.cy, b.w, b.h, (0.12,0.6,0.2,0.95*alpha if hovered else 0.75*alpha), alpha=alpha)
                    elif b.label == "Options":
                        self.draw_rect(b.cx, b.cy, b.w, b.h, (0.12,0.4,0.8,0.95*alpha if hovered else 0.75*alpha), alpha=alpha)
                    else:
                        self.draw_rect(b.cx, b.cy, b.w, b.h, (0.8,0.15,0.2,0.95*alpha if hovered else 0.75*alpha), alpha=alpha)
                # draw text via atlas
                if self.text_renderer:
                    glUseProgram(self.prog_ui)
                    # label positions
                    self.text_renderer.draw_text(self.prog_ui, "MY AWESOME GAME", -0.6, 0.78, color=(1,1,1,1), alpha=alpha)
                    # button labels
                    for b in self.home_buttons:
                        left_x = b.cx - b.w/2 + 0.02
                        top_y = b.cy + b.h/2 - 0.02
                        # focus highlight
                        if getattr(b, "focused", False):
                            # draw outline rect
                            self.draw_rect(b.cx, b.cy, b.w+0.04, b.h+0.04, (1.0,1.0,1.0,0.12*alpha), alpha=alpha)
                        self.text_renderer.draw_text(self.prog_ui, b.label, left_x, top_y, color=(1,1,1,1), alpha=alpha)
                    # FPS
                    self.text_renderer.draw_text(self.prog_ui, f"FPS: {self.fps:.1f}", -0.98, -0.95, color=(1,1,1,1), alpha=alpha)
                    glUseProgram(0)
                else:
                    glfw.set_window_title(self.win, "Home - MY AWESOME GAME")

                # options overlay if open (slide in)
                if self.show_options:
                    # slide offset applied to panel center Y
                    panel_y = lerp(-0.48, 0.04, ease_out_cubic(clamp((self.options_slide + 0.6) / 0.6, 0.0, 1.0)))
                    self.draw_rect(0.0, panel_y, 0.8, 0.46, (0.08,0.08,0.08,0.95*alpha), alpha=alpha)
                    # sliders + knobs
                    for s in self.options_sliders:
                        # use y position offset by panel_y offset delta
                        s_y = s.cy + (panel_y - 0.04)
                        left = s.cx - s.w/2; right = s.cx + s.w/2
                        self.draw_rect(s.cx, s_y, s.w, s.h, (0.2,0.2,0.2,0.95*alpha), alpha=alpha)
                        # knob
                        tnorm = s.normalized()
                        kx = left + tnorm * (right - left)
                        self.draw_rect(kx, s_y, 0.06, s.h+0.02, (0.9,0.9,0.2,1.0*alpha), alpha=alpha)
                        # labels
                        if self.text_renderer:
                            self.text_renderer.draw_text(self.prog_ui, s.label, left+0.02, s_y + s.h/2 - 0.02, alpha=alpha)
                            self.text_renderer.draw_text(self.prog_ui, f"{s.value:.2f}", s.cx + 0.34, s_y + s.h/2 - 0.02, alpha=alpha)
            # MENU (overlay)
            if self.menu_alpha > 0.001:
                alpha = self.menu_alpha
                self.draw_rect(0.0,0.0,2.0,2.0,(0,0,0,0.45*alpha), alpha=alpha)
                # buttons
                for i, b in enumerate(self.menu_buttons):
                    hovered = b.contains(nx, ny)
                    col = (0.12,0.6,0.2,0.95*alpha) if b.label=="Start" else (0.12,0.4,0.8,0.95*alpha) if b.label=="Options" else (0.8,0.15,0.2,0.95*alpha)
                    self.draw_rect(b.cx, b.cy, b.w, b.h, (col[0],col[1],col[2],col[3]*(0.95 if hovered else 0.75)), alpha=alpha)
                if self.text_renderer:
                    glUseProgram(self.prog_ui)
                    for b in self.menu_buttons:
                        left_x = b.cx - b.w/2 + 0.02
                        top_y = b.cy + b.h/2 - 0.02
                        self.text_renderer.draw_text(self.prog_ui, b.label, left_x, top_y, alpha=alpha)
                        if getattr(b, "focused", False):
                            self.draw_rect(b.cx, b.cy, b.w+0.04, b.h+0.04, (1,1,1,0.12*alpha), alpha=alpha)
                    self.text_renderer.draw_text(self.prog_ui, f"FPS: {self.fps:.1f}", -0.98, -0.95, alpha=alpha)
                    glUseProgram(0)
            # PLAYING HUD & Pause
            if self.scene == "playing":
                # hud boxes
                self.draw_rect(-0.82, 0.88, 0.48, 0.12, (0.05,0.05,0.05,0.8))
                # pause box (left)
                self.draw_rect(-0.9, 0.86, 0.12, 0.08, (0.9,0.5,0.0,1.0) if self.paused else (0.2,0.9,0.2,1.0))
                self.draw_rect(-0.74, 0.86, 0.22, 0.08, (0.2,0.6,0.9,1.0))
                if self.text_renderer:
                    glUseProgram(self.prog_ui)
                    self.text_renderer.draw_text(self.prog_ui, "Pause" if self.paused else "Playing", -0.78, 0.95)
                    self.text_renderer.draw_text(self.prog_ui, "Main Menu", -0.78, 0.87)
                    self.text_renderer.draw_text(self.prog_ui, f"FPS: {self.fps:.1f}", 0.8, 0.95)
                    glUseProgram(0)
                # pause menu overlay
                if self.pause_alpha > 0.001:
                    alpha = self.pause_alpha
                    self.draw_rect(0.0,0.0,1.2,1.2,(0.02,0.02,0.02,0.6*alpha), alpha=alpha)
                    # central panel
                    self.draw_rect(0.0, 0.18, 0.64, 0.86, (0.08,0.08,0.08,0.98*alpha), alpha=alpha)
                    # buttons with focus/hover visible
                    for b in self.pause_buttons:
                        hovered = b.contains(nx, ny)
                        col = (0.15,0.7,0.2,0.95*alpha) if b.label=="Resume" else (0.12,0.45,0.85,0.95*alpha) if b.label=="Options" else (0.8,0.4,0.15,0.95*alpha) if b.label=="Main Menu" else (0.9,0.1,0.2,0.95*alpha)
                        self.draw_rect(b.cx, b.cy, b.w, b.h, col, alpha=alpha)
                    # labels
                    if self.text_renderer:
                        glUseProgram(self.prog_ui)
                        for b in self.pause_buttons:
                            left_x = b.cx - b.w/2 + 0.02
                            top_y = b.cy + b.h/2 - 0.02
                            self.text_renderer.draw_text(self.prog_ui, b.label, left_x, top_y, alpha=alpha)
                            if getattr(b, "focused", False):
                                self.draw_rect(b.cx, b.cy, b.w+0.04, b.h+0.04, (1,1,1,0.12*alpha), alpha=alpha)
                        # if options open inside pause, draw them as smaller panel
                        if self.show_options:
                            self.draw_rect(0.0, -0.48, 0.8, 0.36, (0.08,0.08,0.08,0.95*alpha), alpha=alpha)
                            for s in self.options_sliders:
                                self.draw_rect(s.cx, s.cy - 0.48, s.w, s.h, (0.2,0.2,0.2,0.95*alpha), alpha=alpha)
                                kx = s.cx - s.w/2 + s.normalized() * s.w
                                self.draw_rect(kx, s.cy - 0.48, 0.06, s.h+0.02, (0.9,0.9,0.2,1.0*alpha), alpha=alpha)
                                self.text_renderer.draw_text(self.prog_ui, s.label, s.cx - s.w/2 + 0.02, s.cy - 0.48 + s.h/2 - 0.02, alpha=alpha)
                                self.text_renderer.draw_text(self.prog_ui, f"{s.value:.2f}", s.cx + 0.34, s.cy - 0.48 + s.h/2 - 0.02, alpha=alpha)
                        glUseProgram(0)

            # flip buffers
            glfw.swap_buffers(self.win)

        # cleanup
        glDeleteProgram(self.prog_tri)
        glDeleteProgram(self.prog_ui)
        glDeleteBuffers(1, [self.tri_vbo])
        glDeleteVertexArrays(1, [self.tri_vao])
        if GameFullUI.ui_vao:
            glDeleteVertexArrays(1, [GameFullUI.ui_vao])
        if GameFullUI.ui_vbo:
            glDeleteBuffers(1, [GameFullUI.ui_vbo])
        glfw.terminate()

# ---------- run ----------
if __name__ == "__main__":
    app = GameFullUI(1280, 720, "Full OpenGL UI Game (Navigation, Atlas, Transitions)")
    app.run()
