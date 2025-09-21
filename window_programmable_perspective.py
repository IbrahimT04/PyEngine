import glfw
from OpenGL.GL import *
from OpenGL.GL.shaders import compileShader, compileProgram
import numpy as np
from math import sin, cos
import pyrr
from PIL import Image

class Window:


    vertices = np.array([-0.5, -0.5, 0.5,   0.0, 0.0,
                         0.5, -0.5,  0.5,   1.0, 0.0,
                         0.5,  0.5,  0.5,   1.0, 1.0,
                        -0.5,  0.5,  0.5,   0.0, 1.0,

                        -0.5, -0.5, -0.5,   0.0, 0.0,
                         0.5, -0.5, -0.5,   1.0, 0.0,
                         0.5,  0.5, -0.5,   1.0, 1.0,
                        -0.5,  0.5, -0.5,   0.0, 1.0,

                         0.5, -0.5, -0.5,   0.0, 0.0,
                         0.5,  0.5, -0.5,   1.0, 0.0,
                         0.5,  0.5,  0.5,   1.0, 1.0,
                         0.5, -0.5,  0.5,   0.0, 1.0,

                        -0.5,  0.5, -0.5,   0.0, 0.0,
                        -0.5, -0.5, -0.5,   1.0, 0.0,
                        -0.5, -0.5,  0.5,   1.0, 1.0,
                        -0.5,  0.5,  0.5,   0.0, 1.0,

                        -0.5, -0.5, -0.5,   0.0, 0.0,
                         0.5, -0.5, -0.5,   1.0, 0.0,
                         0.5, -0.5,  0.5,   1.0, 1.0,
                        -0.5, -0.5,  0.5,   0.0, 1.0,

                         0.5,  0.5, -0.5,   0.0, 0.0,
                        -0.5,  0.5, -0.5,   1.0, 0.0,
                        -0.5,  0.5,  0.5,   1.0, 1.0,
                         0.5,  0.5,  0.5,   0.0, 1.0],
                            dtype=np.float32)
    indices = np.array([0,  1,  2,      2,  3,  0,
                          4,  5,  6,         6,  7,  4,
                          8,  9, 10,        10, 11,  8,
                         12, 13, 14,        14, 15, 12,
                         16, 17, 18,        18, 19, 16,
                         20, 21, 22,        22, 23, 20],
                            np.uint32)


    def __init__(self, width:int = 1800, height:int = 1200, title:str = "My Window"):
        if not glfw.init():
            raise SystemError("Could not initialize glfw")

        self._win = glfw.create_window(width, height, title, None, None)

        if not self._win:
            glfw.terminate()
            raise SystemError("Could not create glfw window")

        glfw.set_window_pos(self._win, 400, 200)

        glfw.set_window_size_callback(self._win, self.window_resize)

        glfw.make_context_current(self._win)

    def window_resize(self, window, width, height):
        glViewport(0, 0, width, height)
        projection = pyrr.matrix44.create_perspective_projection_matrix(45, width / height, 0.1, 100.0)
        shader = self.shader_program
        proj_location = glGetUniformLocation(shader, 'projection')
        glUniformMatrix4fv(proj_location, 1, GL_FALSE, projection)

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

        vertex_src, fragment_src = self.get_shaders('perspective1')

        shader = compileProgram(compileShader(vertex_src, GL_VERTEX_SHADER), compileShader(fragment_src, GL_FRAGMENT_SHADER))

        self.shader_program = shader

        VBO = glGenBuffers(1)
        glBindBuffer(GL_ARRAY_BUFFER, VBO)
        glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices, GL_STATIC_DRAW)

        EBO = glGenBuffers(1)
        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, EBO)
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL_STATIC_DRAW)

        glEnableVertexAttribArray(0)
        glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, vertices.itemsize * 5, ctypes.c_void_p(0))

        glEnableVertexAttribArray(1)
        glVertexAttribPointer(1, 2, GL_FLOAT, GL_FALSE, vertices.itemsize * 5, ctypes.c_void_p(12))

        texture = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture)

        glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)

        glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)

        image = Image.open("textures/trak_light2.jpg")
        image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

        image_data = image.convert('RGBA').tobytes()
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, image.width, image.height, 0, GL_RGBA, GL_UNSIGNED_BYTE, image_data)

        glUseProgram(shader)
        glClearColor(0, 0.1, 0.1, 1)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

        projection = pyrr.matrix44.create_perspective_projection_matrix(45, 1800/1200, 0.1, 100.0)
        self.trans = pyrr.matrix44.create_from_translation(pyrr.Vector3([0,0,-3]))

        self.model_location = glGetUniformLocation(shader, 'model')
        proj_location = glGetUniformLocation(shader, 'projection')

        glUniformMatrix4fv(proj_location, 1, GL_FALSE, projection)

    def main_loop(self):
        num_indices = len(self.indices)
        model_loc = self.model_location
        translation = self.trans

        while not glfw.window_should_close(self._win):

            glfw.poll_events()

            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

            rot_x = pyrr.Matrix44.from_x_rotation(0.5 * glfw.get_time())
            rot_y = pyrr.Matrix44.from_y_rotation(0.8 * glfw.get_time())

            rotation = pyrr.matrix44.multiply(rot_x, rot_y)
            model = pyrr.matrix44.multiply(rotation, translation)

            glUniformMatrix4fv(model_loc, 1, GL_FALSE, model)

            glDrawElements(GL_TRIANGLES, num_indices, GL_UNSIGNED_INT, ctypes.c_void_p(0))

            glfw.swap_buffers(self._win)

        glfw.terminate()

if __name__ == "__main__":
    window = Window()
    window.draw()
    window.main_loop()