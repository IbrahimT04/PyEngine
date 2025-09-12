import glfw
from OpenGL.GL import *
import numpy as np
from math import sin, cos

class Window:

    vertices = np.array([-0.5, -0.5, 0.0,
                                0.5, -0.5, 0.0,
                                0.0, 0.5, 0.0,],
                                dtype=np.float32)
    colors = np.array([1.0, 0.0, 0.0,
                              0.0, 1.0, 0.0,
                              0.0, 0.0, 1.0,],
                              dtype=np.float32)


    def __init__(self, width:int = 1800, height:int = 1200, title:str = "My Window"):
        if not glfw.init():
            raise SystemError("Could not initialize glfw")

        self._win = glfw.create_window(1800, 1200, title, None, None)

        if not self._win:
            glfw.terminate()
            raise SystemError("Could not create glfw window")

        glfw.set_window_pos(self._win, 400, 200)

        glfw.make_context_current(self._win)

        glClearColor(0, 0.1, 0.1, 1)

    def draw(self):
        vertices = self.vertices
        glEnableClientState(GL_VERTEX_ARRAY)
        glVertexPointer(3, GL_FLOAT, 0, vertices)

        colors = self.colors
        glEnableClientState(GL_COLOR_ARRAY)
        glColorPointer(3, GL_FLOAT, 0, colors)

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

            glDrawArrays(GL_TRIANGLES, 0, 3)

            glfw.swap_buffers(self._win)

        glfw.terminate()

if __name__ == "__main__":
    window = Window()
    window.draw()
    window.main_loop()