import glfw
from OpenGL.GL import *
from OpenGL.GL.shaders import compileShader, compileProgram
import numpy as np
from math import sin, cos
import pyrr

class Window:

    vertices = np.array([-0.5, -0.5, 0.5,     1.0, 0.0, 0.0,
                            0.5, -0.5, 0.5,     0.0, 1.0, 0.0,
                            0.5, 0.5, 0.5,      0.0, 0.0, 1.0,
                            -0.5, 0.5, 0.5,     1.0, 1.0, 1.0,

                            -0.5, -0.5, -0.5,   1.0, 0.0, 0.0,
                            0.5, -0.5, -0.5,    0.0, 1.0, 0.0,
                            0.5, 0.5, -0.5,     0.0, 0.0, 1.0,
                            -0.5, 0.5, -0.5,    1.0, 1.0, 0.0],
                            dtype=np.float32)

    indices = np.array([0, 1, 2,        2, 3, 0,
                            4, 5, 6,      6, 7, 4,
                            4, 5, 1,      1, 0, 4,
                            6, 7, 3,      3, 2, 6,
                            5, 6, 2,      2, 1, 5,
                            7, 4, 0,      0, 3, 7],
                            np.uint32)


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
        indices = self.indices

        vertex_src, fragment_src = self.get_shaders('default')

        shader = compileProgram(compileShader(vertex_src, GL_VERTEX_SHADER), compileShader(fragment_src, GL_FRAGMENT_SHADER))

        VBO = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, VBO)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)

        EBO = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, EBO)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)

        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, 24, ctypes.c_void_p(0))

        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 24, ctypes.c_void_p(12))

        glUseProgram(shader)
        glClearColor(0, 0.1, 0.1, 1)
        glEnable(GL_DEPTH_TEST)

        self.rotation_loc = glGetUniformLocation(shader, 'rotation')

    def main_loop(self):
        num_indices = len(self.indices)
        rot_loc = self.rotation_loc
        while not glfw.window_should_close(self._win):

            glfw.poll_events()

            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            #glDrawArrays(GL_TRIANGLE_STRIP, 0, 4)

            rot_x = pyrr.Matrix44.from_x_rotation(0.5 * glfw.get_time())
            rot_y = pyrr.Matrix44.from_y_rotation(0.8 * glfw.get_time())

            glUniformMatrix4fv(rot_loc, 1, GL_FALSE, pyrr.matrix44.multiply(rot_x, rot_y))

            glDrawElements(GL_TRIANGLES, num_indices, GL_UNSIGNED_INT, ctypes.c_void_p(0))


            glfw.swap_buffers(self._win)

        glfw.terminate()

if __name__ == "__main__":
    window = Window()
    window.draw()
    window.main_loop()