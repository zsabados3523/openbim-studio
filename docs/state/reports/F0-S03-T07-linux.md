# F0-S03 T07: medição com IFC real (Linux)

Arquivo: biblioteca-3pav-ifc4.ifc (317 MB; lido só na máquina do PO, fora do repositório). Medido com `medir.py`, tela virtual (Xvfb, desenho por software), 16 núcleos, 15 threads, blocos de 4000.

| Medida | Resultado | Meta | Situação |
|---|---|---|---|
| Triângulos / produtos com malha | 8.620.328 / 14.804 (6 sem malha) | — | modelo 8,6x maior que o sintético |
| Abrir (tudo carregado) | 405 s | < 60 s | **FALHOU** |
| Primeiro lote visível | 52 s | — | lento |
| Pico de memória | 12.229 MB | < 6 GB | **FALHOU** |
| Memória de vídeo usada | 639 MB | — | ok |
| Atraso máximo da interface | 220 s | pequeno | **FALHOU** (travou) |
| Atraso p95 | 76,6 ms | — | alto |
| FPS | 1,3 | — | sem valor (desenho por software); placa real não medida |

Leitura: o carregador funcionou com 1 milhão de triângulos (T05), mas com um modelo real de 8,6 milhões não cumpre tempo, memória nem responsividade. Há um atraso único de 220 s: algo segura a interface (provavelmente o início da leitura do arquivo ou a conversão em um trecho que não solta o controle). Precisa de investigação antes de concluir se é problema do protótipo (conserta) ou do IfcOpenShell em Python (pede ponte C++).

Falta: Windows; execução na placa real (não feita: 7 min e 12 GB na máquina do PO, aguarda ok); dividir a medição de abrir/ler/converter para achar o gargalo.
Portão da S03: **não atingido com este arquivo** (ver BOARD).

## Investigação do gargalo (opção 1, aprovada pelo PO)
Medido sem interface, só o carregador (15 threads), no mesmo arquivo:
- Abrir o arquivo: 4,4 s. Listar produtos: 0,1 s. Geometria: 370 s (quase todo o tempo).
- De 290 s de geometria no teste por bloco, **~240 s estão no bloco 2 (produtos 4000 a 8000)** e um único passo levou 178 s.
- Culpados (passos acima de 5 s), todos peças de mobiliário/forro que vêm como "item mapeado" (família repetida): máquina de café ("MAQUINA DE CAFE", ~160 s), poltrona Gio Ponti (~20 s), montante de forro (~5 s). A geometria dessas peças é muito detalhada e a conversão do IfcOpenShell (OpenCascade) demora; enquanto isso o Python fica preso e a interface trava (as travadas de 40 s e 215 s).
- Sem essas peças, o resto converte em cerca de 100 s (8,6M triângulos), ainda acima de 60 s mas perto.

Conclusão: o problema não é o desenho nem a ponte, e sim **poucas peças patológicas** e o fato de a conversão prender o Python. Caminhos (cartão novo):
1. Rodar a conversão em **processo separado** (não prende a interface) e/ou com **limite de tempo por peça**: peça lenta vira caixa simples e a gente segue.
2. Usar a geração de malha mais simples (sem OpenCascade, `geometry_library="hybrid-cgal-simple-opencascade"` ou similar) e comparar tempo.
3. Medir memória depois de (1): 12 GB provavelmente vem de segurar tudo em Python; reavaliar.
