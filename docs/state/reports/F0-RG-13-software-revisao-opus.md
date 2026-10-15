# Revisão Opus: F0-RG-13, parte C++ (desenho por software sem placa de vídeo, PR 115)

- Data: 2026-10-15
- PR: #115, ramo do PR em `461ee4b`
- Cartão: F0-RG-13 em `docs/state/reports/F0-REVISAO-GERAL-2026-10-15.md` (achado B25)
- Revisor: Opus (não escreveu nada desta tarefa)
- Diff revisado: `prototypes/s04/obimcore/nucleo/motor.h` (+15 −2), `prototypes/s04/obimcore/ponte_viewport.cpp` (+2 −1), `tests/test_s04_viewport.py` (+1), `tests/test_s04_viewport_software.py` (novo, 18 linhas)
- `v2/` e `CLAUDE.md`: não mudam neste PR (conferido no diff contra `main`).
- CI: na fila quando a revisão foi feita. A autora não compilou; só o CI do Windows e do Linux compila o C++.
- Como foi conferido: leitura do diff, de `motor.h` (criação do desenho), dos auxiliares de teste da viewport e de `.github/workflows/ci.yml` (quais passos rodam quais arquivos de teste e com que variáveis).

## Veredito: REPROVADO

O caminho com placa de vídeo não muda e o oráculo da S04 não muda. Mas o teste novo nunca roda no CI, e o aviso pode aparecer no caso errado.

## O que está certo

1. Com placa de vídeo, o caminho é o mesmo de antes: `abrir(fl)` faz a mesma chamada de `QRhi::create` com as mesmas opções; só se acrescenta o cálculo de `software_`.
2. `software_` é `std::atomic<bool>`: gravado na thread de desenho, lido na thread da janela, sem corrida. É recalculado a cada nova criação (perda da placa inclusive).
3. `test_s04_viewport.py` só acrescenta uma chave ao resultado do caso `imagem`; nenhum número nem conferência do oráculo muda.
4. Ponte: as duas funções novas são só leitura e não tocam no Python fora da thread da janela.

## Correções exigidas

1. **O teste novo nunca roda no CI.** `tests/test_s04_viewport_software.py` não está em nenhuma lista dos passos da viewport (`ci.yml:144`, `:310`, `:348`), que são os únicos com o `obimcore` compilado. Nos passos gerais (`pytest -q tests`, `ci.yml:77` e `:207`) o módulo não existe e a fixture `viewport` pula. Resultado: a conferência com WARP (`QSG_RHI_PREFER_SOFTWARE_RENDERER=1`) nunca é feita, e qualquer quebra do aviso passa. Correção: acrescentar o arquivo à lista do passo da viewport no Linux (`ci.yml:144`) e no job `windows-viewport-b` (`ci.yml:348`, que já liga o WARP). Trocar também o `pytest.skip` de "aviso() ausente" pela `guarda`/`pular` da S04, para falhar quando `OBIM_S04_OBRIGATORIO=1`.
2. **O aviso pode aparecer com placa de vídeo.** `software_ = por_software || ...`, e `por_software` fica verdadeiro só porque a opção "preferir software" foi pedida. No OpenGL (Linux, e Windows quando `gl_`) o Qt ignora essa opção: a segunda tentativa usa o mesmo driver, e se ela der certo o usuário vê "sem placa de vídeo" com placa de vídeo. O mesmo acontece com a variável `QSG_RHI_PREFER_SOFTWARE_RENDERER` ligada e OpenGL com placa. Correção: (a) fazer a segunda tentativa só no Direct3D 11 (`!gl_`); (b) decidir `software_` pelo que o Qt informa do dispositivo, não pelo pedido: `deviceType == QRhiDriverInfo::CpuDevice` ou nome do dispositivo contendo `llvmpipe`, `softpipe`, `SwiftShader` ou `Microsoft Basic Render` (no OpenGL o `deviceType` pode vir sem valor; o nome é o que identifica com certeza o Mesa por software no Linux).
3. **Conferência no Linux.** Depois do item 2, no passo do Linux (que roda com `LIBGL_ALWAYS_SOFTWARE=1`, Mesa `llvmpipe`) o teste deve exigir `software is True` e "software" no aviso, do mesmo jeito que o Windows com WARP. Assim o teste falha nos dois sistemas se `aviso()` voltar vazio ou `desenho_por_software()` voltar falso.

## Recomendado (não bloqueia)

4. A segunda tentativa (placa ausente → software) não tem como ser exercitada no CI, porque o Windows sempre tem o adaptador WARP. Um gancho de teste (variável que faz a primeira criação falhar) cobriria esse caminho; pode ficar para a S04 retomada.
5. Quando a criação falha de vez (`return false`), `software_` guarda o valor anterior. Zerar antes de tentar evita aviso velho.
6. A mensagem do aviso está em pt-BR fixa no C++. Quando houver tradução, o texto deve sair do lado Python/Qt; por ora serve.

## Para o implementador

Arquivos permitidos: `prototypes/s04/obimcore/nucleo/motor.h` (só a criação do desenho e `software()`/`aviso()`), `tests/test_s04_viewport_software.py` e, em `.github/workflows/ci.yml`, só acrescentar o arquivo de teste às listas das linhas 144 e 348. Não mexer nos outros testes da S04 nem nos limites do oráculo. Só aprovar de novo com o CI obrigatório verde de verdade (o C++ só compila lá). Depois volta para nova revisão Opus (T3).

---

# Segunda revisão (commit `1ca7afb`)

## Veredito: APROVADO (a mesclagem continua dependendo do CI obrigatório verde)

1. **O teste roda no CI: feito.** O arquivo entrou na lista do `windows-viewport-b` (com WARP) e numa linha própria no passo da viewport do Linux (`LIBGL_ALWAYS_SOFTWARE=1`, `llvmpipe`). A guarda da S04 troca o "pular" por falha com `OBIM_S04_VIEWPORT_OBRIGATORIO=1`, então CI verde quer dizer que o teste rodou. Conferido no registro do `windows-viewport-b`: "209 passed, 2 skipped", e os dois pulos são de `test_s04_metas.py`.
2. **Aviso só no caso certo: feito.** A segunda tentativa só acontece no Direct3D 11 (`#ifdef Q_OS_WIN` e `!gl_`). `software_` vem do dispositivo (`CpuDevice` ou nome com `llvmpipe`, `softpipe`, `SwiftShader`, `Microsoft Basic Render`) ou da segunda tentativa, que só existe no Direct3D, onde ela de fato usa o WARP.
3. **Conferência nos dois sistemas: feito.** Com WARP ou com `LIBGL_ALWAYS_SOFTWARE=1`, o teste exige `software is True` e "software" no aviso. Se `aviso()` voltar vazio ou `desenho_por_software()` voltar falso, o teste falha nos dois.
4. **Item 5 (recomendado) também feito:** `software_` é zerado antes de cada criação.

Com placa de vídeo o caminho continua igual: mesma criação, e o aviso só aparece se o dispositivo for de software.
