# ui_debug_test.py
"""
Minimal OpenGL UI test
- verifies shaders compile
- draws a Home-like screen with 3 big buttons (colored rectangles)
- prints Pillow / atlas status and GL errors
Run: python ui_debug_test.py
Requires: glfw, PyOpenGL (Pillow optional)
"""
import glfw, sys, time
from OpenGL.GL import *
import ctypes
import numpy as np

# --- helpers ---
def compile_shader(src, kind):
    sh = glCreateShader(kind)
    glShaderSource(sh, src)
    glCompileShader(sh)
    ok = glGetShaderiv(sh, GL_COMPILE_STATUS)
    log = glGetShaderInfoLog(sh)
    if isinstance(log, bytes):
        log = log.decode()
    return sh, bool(ok), log

def link_program(vs, fs):
    prog = glCreateProgram()
    glAttachShader(prog, vs)
    glAttachShader(prog, fs)
    glLinkProgram(prog)
    ok = glGetProgramiv(prog, GL_LINK_STATUS)
    log = glGetProgramInfoLog(prog)
    if isinstance(log, bytes):
        log = log.decode()
    return prog, bool(ok), log


VERT = """
#version 330 core
layout(location=0) in vec2 a_pos;
uniform mat4 u_proj;
void main(){ gl_Position = u_proj * vec4(a_pos,0,1); }
"""
FRAG = """
#version 330 core
uniform vec4 u_color;
out vec4 o_col;
void main(){ o_col = u_color; }
"""

def print_gl_error(stage=""):
    err = glGetError()
    if err != GL_NO_ERROR:
        print("GL ERROR", stage, hex(err))

# --- init glfw + GL ---
if not glfw.init():
    print("glfw.init failed"); sys.exit(1)

# request 3.3 core to match your app
glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)

win = glfw.create_window(800, 600, "UI Debug Test", None, None)
if not win:
    glfw.terminate(); print("create_window failed"); sys.exit(1)
glfw.make_context_current(win)
glViewport(0,0,800,600)
glClearColor(0.06, 0.08, 0.10, 1.0)
glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

# compile simple UI shader
vs, ok_vs, log_vs = compile_shader(VERT, GL_VERTEX_SHADER)
fs, ok_fs, log_fs = compile_shader(FRAG, GL_FRAGMENT_SHADER)
print("Vertex compile ok:", ok_vs);
if log_vs: print("VS log:", log_vs)
print("Fragment compile ok:", ok_fs);
if log_fs: print("FS log:", log_fs)
prog, ok_prog, log_prog = link_program(vs, fs)
print("Program link ok:", ok_prog)
if log_prog: print("Link log:", log_prog)
if not (ok_vs and ok_fs and ok_prog):
    print("Shader build failed — see logs above. Exiting.")
    glfw.terminate(); sys.exit(1)
print_gl_error("after shader build")

# make a VAO/VBO for a rectangle (we'll upload per-rect)
vao = glGenVertexArrays(1)
vbo = glGenBuffers(1)
glBindVertexArray(vao)
glBindBuffer(GL_ARRAY_BUFFER, vbo)
# allocate space (6 verts * 2 floats)
glBufferData(GL_ARRAY_BUFFER, 6 * 2 * ctypes.sizeof(ctypes.c_float), None, GL_DYNAMIC_DRAW)
glEnableVertexAttribArray(0)
glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 2 * ctypes.sizeof(ctypes.c_float), ctypes.c_void_p(0))
glBindBuffer(GL_ARRAY_BUFFER, 0)
glBindVertexArray(0)
print_gl_error("vao/vbo create")

# simple orthographic projection (identity since we feed clip coords)
proj = np.eye(4, dtype=np.float32)

def draw_rect(cx, cy, w, h, color):
    left = cx - w/2; right = cx + w/2; top = cy + h/2; bottom = cy - h/2
    verts = np.array([
        left, bottom,
        right, bottom,
        right, top,
        left, bottom,
        right, top,
        left, top,
    ], dtype=np.float32)
    glUseProgram(prog)
    # upload
    glBindVertexArray(vao)
    glBindBuffer(GL_ARRAY_BUFFER, vbo)
    glBufferSubData(GL_ARRAY_BUFFER, 0, verts.nbytes, verts)
    # uniforms
    loc = glGetUniformLocation(prog, "u_proj")
    glUniformMatrix4fv(loc, 1, GL_FALSE, proj)
    locc = glGetUniformLocation(prog, "u_color")
    glUniform4f(locc, *color)
    glDrawArrays(GL_TRIANGLES, 0, 6)
    glBindBuffer(GL_ARRAY_BUFFER, 0)
    glBindVertexArray(0)
    glUseProgram(0)

# UI layout in NDC coords
# Top title rect
title_rect = (0.0, 0.6, 1.6, 0.34)
btn_start = (0.0, 0.2, 1.0, 0.28)
btn_options = (0.0, -0.05, 1.0, 0.28)
btn_quit = (0.0, -0.35, 1.0, 0.28)

print("Pillow available:", end=" ")
try:
    from PIL import Image
    print("Yes")
except Exception:
    print("No (text will be shown in window title instead)")

# Force scene to home
scene = "home"

while not glfw.window_should_close(win):
    glfw.poll_events()
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

    if scene == "home":
        # background subtle triangle: just clear color + overlay
        # draw dark overlay
        draw_rect(0.0, 0.0, 2.0, 2.0, (0.0,0.0,0.0,0.2))
        # title rect
        draw_rect(*title_rect, (0.02,0.02,0.04,0.9))
        # Start, Options, Quit large buttons (distinct colors)
        draw_rect(*btn_start, (0.15,0.7,0.2,1.0))
        draw_rect(*btn_options, (0.15,0.45,0.85,1.0))
        draw_rect(*btn_quit, (0.9,0.2,0.25,1.0))

        # If Pillow installed you could draw text; otherwise update title so user sees labels
        try:
            from PIL import Image, ImageFont, ImageDraw
            # we won't render text into GL now — keep minimal
            pass
        except Exception:
            glfw.set_window_title(win, "Home - Start / Options / Quit")

    glfw.swap_buffers(win)

print("Shutting down")
glDeleteBuffers(1, [vbo])
glDeleteVertexArrays(1, [vao])
glDeleteProgram(prog)
glfw.terminate()
