#version 330 core

in vec3 gen_color;

out vec4 out_color;

void main() {
    out_color = vec4(gen_color, 1.0);
}