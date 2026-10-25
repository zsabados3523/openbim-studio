// SPDX-License-Identifier: AGPL-3.0-or-later
#version 440
layout(location = 0) in vec3 position;
layout(location = 1) in vec3 normal;
layout(location = 2) in vec4 color;
layout(location = 0) out vec4 v_color;
layout(std140, binding = 0) uniform buf {
    mat4 mvp;
    vec4 luz; // direção da câmera (do olho para a cena), no mundo
} ubuf;
void main()
{
    float k = 0.35 + 0.65 * abs(dot(normalize(normal), ubuf.luz.xyz));
    v_color = vec4(color.rgb * k, color.a);
    gl_Position = ubuf.mvp * vec4(position, 1.0);
}
