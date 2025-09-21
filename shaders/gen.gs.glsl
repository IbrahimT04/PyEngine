#version 330 core

layout (triangles) in;
layout (triangle_strip, max_vertices = 12) out;

in vec3 v_color[];   // from vertex shader
out vec3 gen_color;  // to fragment shader

void main() {
    for (int i = 0; i < 3; ++i) {
        // Quad for each input vertex (4 verts)
        gl_Position = gl_in[i].gl_Position + vec4(-0.1, -0.1, 0.0, 0.0);
        gen_color = v_color[i];
        EmitVertex();

        gl_Position = gl_in[i].gl_Position + vec4(0.1, -0.1, 0.0, 0.0);
        gen_color = v_color[i];
        EmitVertex();

        gl_Position = gl_in[i].gl_Position + vec4(-0.1, 0.1, 0.0, 0.0);
        gen_color = v_color[i];
        EmitVertex();

        gl_Position = gl_in[i].gl_Position + vec4(0.1, 0.1, 0.0, 0.0);
        gen_color = v_color[i];
        EmitVertex();

        EndPrimitive();
    }
}
