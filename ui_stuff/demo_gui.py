# demo_gui.py
# Full OpenGL UI demo with Home Screen, Options, and Pause Menu
# Requires: glfw, PyOpenGL, Pillow
import glfw
from OpenGL.GL import *
import numpy as np
from math import sin, cos
from PIL import Image, ImageDraw, ImageFont

# Simple shader program for colored triangles (modern OpenGL)
VERT_SHADER_SRC = """
#version 330 core
layout(location = 0) in vec3 position;
layout(location = 1) in vec3 color;
uniform float scale;
uniform float time;
out vec3 v_color;
void main() {
    float t = time;
    float s = abs(sin(t)) * 0.5 * scale + 0.3;
    float x = sin(t) * 0.5 + position.x * s;
    float y = cos(t) * 0.25 + position.y * s;
    gl_Position = vec4(x, y, position.z, 1.0);
    v_color = color;
}
"""
FRAG_SHADER_SRC = """
#version 330 core
in vec3 v_color;
out vec4 FragColor;
void main() {
    FragColor = vec4(v_color, 1.0);
}
"""

# Helper to compile shader
def compile_shader(src, sh_type):
    sh = glCreateShader(sh_type)
    glShaderSource(sh, src)
    glCompileShader(sh)
    status = glGetShaderiv(sh, GL_COMPILE_STATUS)
    if not status:
        print(glGetShaderInfoLog(sh))
    return sh, bool(status)

# Button class for fallback UI
class Button:
    def __init__(self, x, y, w, h, label):
        self.x, self.y, self.w, self.h = x, y, w, h  # NDC coords
        self.label = label

    def contains(self, nx, ny):
        return (self.x - self.w/2 <= nx <= self.x + self.w/2 and
                self.y - self.h/2 <= ny <= self.y + self.h/2)

# Text rendering using Pillow to texture
class TextRenderer:
    def __init__(self):
        self.font = ImageFont.load_default()
        self.cache = {}

    def create_texture(self, text, color=(255,255,255)):
        if text in self.cache:
            return self.cache[text]
        img = Image.new("RGBA", (256, 64), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        draw.text((0,0), text, font=self.font, fill=color+(255,))
        tex = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, tex)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, img.width, img.height, 0,
                     GL_RGBA, GL_UNSIGNED_BYTE, img.tobytes())
        self.cache[text] = (tex, img.width, img.height)
        return tex, img.width, img.height

    def draw_text(self, text, x, y, scale=1.0):
        tex, w, h = self.create_texture(text)
        glEnable(GL_TEXTURE_2D)
        glBindTexture(GL_TEXTURE_2D, tex)
        glBegin(GL_QUADS)
        glTexCoord2f(0,0); glVertex2f(x, y)
        glTexCoord2f(1,0); glVertex2f(x + w/300*scale, y)
        glTexCoord2f(1,1); glVertex2f(x + w/300*scale, y + h/300*scale)
        glTexCoord2f(0,1); glVertex2f(x, y + h/300*scale)
        glEnd()
        glDisable(GL_TEXTURE_2D)

# Main UI class
class GameFullUI:
    def __init__(self, width=1280, height=720, title="Demo UI"):
        if not glfw.init():
            raise RuntimeError("glfw.init failed")
        self.width = width
        self.height = height
        self._win = glfw.create_window(width, height, title, None, None)
        if not self._win:
            glfw.terminate()
            raise RuntimeError("Failed to create window")
        glfw.set_window_pos(self._win, 200, 100)
        glfw.make_context_current(self._win)
        glfw.swap_interval(1)
        glClearColor(0.06, 0.08, 0.10, 1.0)
        glEnable(GL_DEPTH_TEST)

        # Compile shader
        vs, ok_vs = compile_shader(VERT_SHADER_SRC, GL_VERTEX_SHADER)
        fs, ok_fs = compile_shader(FRAG_SHADER_SRC, GL_FRAGMENT_SHADER)
        self.program = glCreateProgram()
        glAttachShader(self.program, vs)
        glAttachShader(self.program, fs)
        glLinkProgram(self.program)
        self.linked = glGetProgramiv(self.program, GL_LINK_STATUS)
        glDeleteShader(vs)
        glDeleteShader(fs)

        # Triangle data
        self.vertices = np.array([-0.5,-0.5,0, 0.5,-0.5,0, 0,0.5,0], dtype=np.float32)
        self.colors = np.array([1,0,0, 0,1,0, 0,0,1], dtype=np.float32)
        self.vao = glGenVertexArrays(1)
        self.vbo = glGenBuffers(2)
        glBindVertexArray(self.vao)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo[0])
        glBufferData(GL_ARRAY_BUFFER, self.vertices.nbytes, self.vertices, GL_STATIC_DRAW)
        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, False, 0, None)
        glBindBuffer(GL_ARRAY_BUFFER, self.vbo[1])
        glBufferData(GL_ARRAY_BUFFER, self.colors.nbytes, self.colors, GL_STATIC_DRAW)
        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1,3,GL_FLOAT,False,0,None)
        glBindVertexArray(0)

        # State
        self.scene = "menu"
        self.paused = False
        self.show_options = False
        self.tri_scale = 1.0
        self.tri_speed = 1.0
        self.counter = 0
        self.pause_menu_open = False

        # Buttons
        self.home_buttons = [
            Button(0, 0.25, 1.2, 0.28, "Start"),
            Button(0, -0.05, 1.2, 0.28, "Options"),
            Button(0, -0.35, 1.2, 0.28, "Quit"),
        ]
        self.pause_buttons = [
            Button(0, 0.1, 1.0, 0.25, "Resume"),
            Button(0, -0.1, 1.0, 0.25, "Options"),
            Button(0, -0.3, 1.0, 0.25, "Main Menu"),
        ]
        self.text = TextRenderer()
        glfw.set_mouse_button_callback(self._win, self._on_mouse)
        glfw.set_key_callback(self._win, self._on_key)

    def start_game(self):
        self.scene = "playing"
        self.paused = False
        self.pause_menu_open = False

    def resume_from_pause(self):
        self.paused = False
        self.pause_menu_open = False

    def quit_game(self):
        glfw.set_window_should_close(self._win, True)

    def _on_key(self, win, key, sc, act, mods):
        if act != glfw.PRESS: return
        if key == glfw.KEY_ESCAPE:
            if self.scene=="playing" and self.paused:
                self.resume_from_pause()
            elif self.scene=="playing":
                self.scene="menu"
            else:
                self.quit_game()
        elif key in (glfw.KEY_ENTER, glfw.KEY_KP_ENTER):
            if self.scene=="menu": self.start_game()
        elif key is glfw.KEY_O:
            self.show_options = not self.show_options
        elif key is glfw.KEY_Q:
            self.quit_game()
        elif key == glfw.KEY_P:
            if self.scene=="playing":
                self.paused = not self.paused
                self.pause_menu_open = self.paused

    def _on_mouse(self, win, button, action, mods):
        if button!=glfw.MOUSE_BUTTON_LEFT or action!=glfw.PRESS: return
        mx,my = glfw.get_cursor_pos(self._win)
        nx = (mx/self.width)*2 -1
        ny = -((my/self.height)*2 -1)
        if self.scene=="menu":
            for b in self.home_buttons:
                if b.contains(nx, ny):
                    if b.label=="Start": self.start_game()
                    elif b.label=="Options": self.show_options=True
                    elif b.label=="Quit": self.quit_game()
        elif self.scene=="playing" and self.pause_menu_open:
            for b in self.pause_buttons:
                if b.contains(nx, ny):
                    if b.label=="Resume": self.resume_from_pause()
                    elif b.label=="Options": self.show_options=True
                    elif b.label=="Main Menu": self.scene="menu"; self.paused=False; self.pause_menu_open=False

    def draw_triangle(self, time_sec):
        glUseProgram(self.program)
        glBindVertexArray(self.vao)
        loc_scale = glGetUniformLocation(self.program,"scale")
        loc_time = glGetUniformLocation(self.program,"time")
        glUniform1f(loc_scale,self.tri_scale)
        glUniform1f(loc_time,time_sec*self.tri_speed)
        glDrawArrays(GL_TRIANGLES,0,3)
        glBindVertexArray(0)
        glUseProgram(0)

    def _draw_buttons(self, buttons):
        glMatrixMode(GL_PROJECTION)
        glPushMatrix(); glLoadIdentity()
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix(); glLoadIdentity()
        glDisable(GL_DEPTH_TEST)
        for b in buttons:
            glColor4f(0.2,0.7,0.2,0.8)
            glBegin(GL_TRIANGLES)
            l,r,t,bm = b.x-b.w/2,b.x+b.w/2,b.y+b.h/2,b.y-b.h/2
            glVertex2f(l,bm); glVertex2f(r,bm); glVertex2f(r,t)
            glVertex2f(l,bm); glVertex2f(r,t); glVertex2f(l,t)
            glEnd()
            # draw label
            self.text.draw_text(b.label, l+0.05, bm+0.05, 1.0)
        glEnable(GL_DEPTH_TEST)
        glPopMatrix(); glMatrixMode(GL_PROJECTION); glPopMatrix(); glMatrixMode(GL_MODELVIEW)

    def run(self):
        while not glfw.window_should_close(self._win):
            glfw.poll_events()
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
            t = glfw.get_time()
            if self.scene in ("menu","playing"):
                self.draw_triangle(t)
            if self.scene=="menu":
                self._draw_buttons(self.home_buttons)
            if self.scene=="playing" and self.paused and self.pause_menu_open:
                self._draw_buttons(self.pause_buttons)
            glfw.swap_buffers(self._win)
        glfw.terminate()

if __name__=="__main__":
    app = GameFullUI(1280,720,"Demo Full UI")
    app.run()
