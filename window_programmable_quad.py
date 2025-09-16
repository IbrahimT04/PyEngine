import glfw
from OpenGL.GL import *
from OpenGL.GL.shaders import compileShader, compileProgram
import numpy as np
from math import sin, cos

class Window:

    vertices = np.array([-0.5, -0.5, 0.0,    1.0, 0.0, 0.0,
                                0.5, -0.5, 0.0,     0.0, 1.0, 0.0,
                                -0.5, 0.5, 0.0,     0.0, 0.0, 1.0,
                                0.5, 0.5, 0.0,      1.0, 1.0, 1.0],
                                dtype=np.float32)


    def __init__(self, width:int = 1800, height:int = 1200, title:str = "My Window"):
        if not glfw.init():
            raise SystemError("Could not initialize glfw")

        self._win = glfw.create_window(width, height, title, None, None)

        if not self._win:
            glfw.terminate()
            raise SystemError("Could not create glfw window")

        glfw.set_window_pos(self._win, 400, 200)

        glfw.set_window_size_callback(self._win, Window.window_resize)

        glfw.make_context_current(self._win)

        glClearColor(0, 0.1, 0.1, 1)

    @staticmethod
    def window_resize(window, width, height):
        glViewport(0, 0, width, height)

    @staticmethod
    def get_shaders(shader_program_name):
        with open(f'shaders/{shader_program_name}.vert') as file:
            vertex_shader = file.read()
        with open(f'shaders/{shader_program_name}.frag') as file:
            fragment_shader = file.read()

        return vertex_shader, fragment_shader

    def draw(self):
        vertices = self.vertices

        vertex_src, fragment_src = self.get_shaders('old')

        shader = compileProgram(compileShader(vertex_src, GL_VERTEX_SHADER), compileShader(fragment_src, GL_FRAGMENT_SHADER))

        VBO = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, VBO)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)

        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 24, ctypes.c_void_p(0))

        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 24, ctypes.c_void_p(12))

        glUseProgram(shader)



    def main_loop(self):
        while not glfw.window_should_close(self._win):

            glfw.poll_events()

            glClear(GL_COLOR_BUFFER_BIT)

            ct = glfw.get_time()

            glLoadIdentity()
            glScale(abs(sin(ct)), abs(sin(ct)), 1)
            glRotatef(sin(ct) * 45, 0, 0, 1)
            glTranslate(sin(ct), cos(ct), 0)

            # glRotatef( abs(sin(ct) * 0.1), 0, 1, 0)

            glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)

            glfw.swap_buffers(self._win)

        glfw.terminate()

if __name__ == "__main__":
    window = Window()
    window.draw()
    window.main_loop()