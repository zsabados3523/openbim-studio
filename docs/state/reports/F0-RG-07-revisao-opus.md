# Revisão Opus: F0-RG-07 (deslocamento da cena, PR 104)

- Data: 2026-10-15
- PR: #104, ramo do PR em `8bd293d`
- Cartão: F0-RG-07 em `docs/state/reports/F0-REVISAO-GERAL-2026-10-15.md` (achado B6)
- Revisor: Opus (não escreveu nada desta tarefa)
- Diff revisado: `prototypes/s04/fluxo_a/fluxo_a.py` (+7 −2), `prototypes/s04/fluxo_a/CONTRATO.md` (+1), `tests/test_s04_fluxo_a.py` (+20)
- `v2/` e `CLAUDE.md`: não mudam neste PR (conferido no diff contra `main`).
- CI: ainda na fila quando a revisão foi feita; o veredito abaixo não depende dele.

## Veredito: REPROVADO

O cálculo está certo. O problema é o que ele muda em volta: a câmera.

## O que está certo

1. Conta em float64 até o fim: `pos - desl` é feito em float64 e só depois vira float32. Posição relativa fica pequena, erro de float32 cai para micrômetros.
2. Deslocamento arredondado ao metro (`np.rint`), igual ao S03 (`processo_malhas.py:174-178`). A geometria do `obimcore.malhas` vem em metros (`UseWorldCoords`, conversão de unidade do ifcopenshell), então "ao metro" está correto.
3. Um deslocamento só por sessão (`self._desl`), passado em todo `LoteMalha`. Isso casa com a regra da `Cena` C++, que recusa lote com deslocamento diferente do primeiro (`cena.cpp:89,115`). Desfazer, refazer, apagar e lotes de 500 na abertura usam o mesmo valor.
4. Seleção: a `Cena` já soma o deslocamento de cada lote na seleção (`test_s04_selecao_c.py:309`). Nada a mudar ali.
5. Coordenada negativa e deslocamento enorme: `rint` e float64 funcionam igual para negativos e até ~1e15 m. Sem risco.
6. O teste novo é real: no CI roda no passo com `OBIM_S04_T11_OBRIGATORIO=1`, então se o `obimcore` faltar ele FALHA em vez de pular. Ele confere ida e volta (lote + deslocamento = geometria do ifcopenshell, tolerância 1 mm), posições pequenas e o mesmo deslocamento em dois lotes.

## Correções exigidas

1. **A câmera ficou em outro sistema de coordenadas sem ninguém ajustar quem a usa.** Antes do PR, `camera{alvo}` era coordenada do mundo (deslocamento zero). Agora `_c_camera` (`fluxo_a.py:378-380`) manda o alvo direto para a cena, que está em "mundo menos deslocamento". O teste `test_desfazer_e_refazer_devolvem_cena_imagem_e_selecao_ao_estado_anterior` (`tests/test_s04_fluxo_a.py:698-705`, caso `c_cena` em `tests/s04_fluxo_aux.py:226-233`) ainda passa o alvo `[7.0, 0.075, 1.4]` em coordenada do mundo. Com o PR, o 1º lote (parede 0, de x=0 a 4) fixa o deslocamento em (2, 0, 1), e o alvo vira o ponto do mundo (9, 0.075, 2.4): exatamente a face lateral da parede 1 (x de 5 a 9). O raio do centro da tela corre em cima da face (azimute −90 não muda o x). A conferência `sel["centro"] == g1` passa a depender de arredondamento: falha ou fica instável. Mesmo que passe, passa pelo motivo errado.
   **Correção:** o comando `camera` do fluxo A recebe e devolve coordenadas do **mundo**; `_c_camera` converte para a cena subtraindo `self._desl`. Se `self._desl` ainda é `None` quando chega o comando (modelo sem geometria ainda), fixar `self._desl = np.rint(alvo)` (o ponto para onde se olha é um bom centro da cena) antes de mandar para a `Cena`. Atualizar a linha do `CONTRATO.md` para dizer "`camera{alvo}` em coordenadas do mundo; o fluxo converte". Não mexer no `s04_fluxo_aux.py` nem no teste de `c_cena` (são oráculo).
2. **Falta teste com a janela e coordenada UTM.** O teste novo usa `janela=False` e chama `_lote` direto; nunca passa pela `Cena` C++ com um modelo longe da origem. Acrescentar um caso com tela (mesmo padrão de `c_cena`): criar 3 paredes, mover para (333000, 7400000, 0) **antes** do 1º lote ir à cena (ou abrir uma base já em UTM), pôr a câmera com alvo em coordenada do mundo no meio da parede do meio, e conferir: (a) nenhum `adicionar_lote`/`atualizar` recusado; (b) `selecionar` no centro devolve a parede do meio; (c) depois de `mover` uma parede 1 m, o desenho muda (pixels) e a seleção continua certa. Esse caso é o que pega tremor e seleção errada, que é o problema do achado B6.
3. **Teste unitário: incluir coordenada negativa.** No teste novo, repetir a conta com (−333000, −7400000, −50). Custa uma linha de laço e fecha o caso de borda que o cartão pede.

## Observação (não bloqueia; para o RG-04 ou depois da S04)

4. O deslocamento vem do 1º bloco de 500 produtos. Modelo com vários terrenos muito longe um do outro (dezenas de km) fica com o terreno distante menos preciso: a 100 km do centro o degrau do float32 é ~8 mm; a 1.000 km, ~6 cm. O S03 tem o mesmo limite. Para casas e prédios do Brasil (um terreno) não afeta. Registrar no cartão do RG-04 (formato único entre S03 e S04): calcular o deslocamento a partir de `IfcMapConversion`/`IfcSite` ou da caixa do modelo inteiro, e no futuro um deslocamento por terreno.

## Para o implementador

Arquivos permitidos: `prototypes/s04/fluxo_a/fluxo_a.py`, `prototypes/s04/fluxo_a/CONTRATO.md`, `tests/test_s04_fluxo_a.py` (só os testes novos do RG-07). Não editar `tests/s04_fluxo_aux.py` nem os testes antigos. Depois das correções, volta para nova revisão Opus (T3).
