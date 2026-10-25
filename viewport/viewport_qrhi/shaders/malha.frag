// SPDX-License-Identifier: AGPL-3.0-or-later
#version 440
layout(location = 0) in vec4 v_color;
layout(location = 0) out vec4 fragColor;
void main()
{
    fragColor = vec4(v_color.rgb, 1.0); // transparência é carregada, mas desenhada opaca.
}
