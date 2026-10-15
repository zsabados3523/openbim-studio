# Revisão Opus: F0-RG-04 (formato único de geometria e foto do arquivo, PRs 123 e 125)

- Data: 2026-10-15
- PRs: #123 (ramo `claude/rg-04-formato-malha`, `6ee0644`) e #125 (ramo `claude/rg-04-foto-arquivo`, `57b0efd`)
- Cartão: F0-RG-04 em `docs/state/reports/F0-REVISAO-GERAL-2026-10-15.md` (achados B2, B23, B32)
- Revisor: Opus (não escreveu nada desta tarefa; autor: conversa "Cartões restantes da revisão")
- `v2/` e `CLAUDE.md`: não mudam em nenhum dos dois PRs (conferido no diff contra `main`).
- CI: em andamento quando a revisão foi feita; o veredito abaixo não depende dele.
- Como foi conferido: leitura dos dois diffs e dos três lugares do C++ que repetem o formato (`cena.h`, `cena.cpp`, `motor.h`, `ponte_viewport.cpp`). Testes puros rodados aqui com Python 3.13 + numpy, sem pytest; checagem por mutação (abaixo). Os testes que precisam do IfcOpenShell e de processo filho não rodam neste ambiente; foram avaliados lendo o caminho.

## Veredito

- **PR 123: REPROVADO** (o teste não confere duas das quatro cópias do formato no C++).
- **PR 125: REPROVADO** (soma calculada à toa em toda carga; um dos três usos da foto sem teste).

## PR 123: o que está certo

1. `prototypes/formato_malha.py` é Python puro, com os dois formatos e o `LoteMalha`; o carregador, a janela da S03 e o fluxo A importam dali. O fluxo A não depende mais da S03 (o teste confere pelo texto).
2. Os nomes que o processo filho usa ficaram públicos (`montar_lote`, `paleta_da_peca`, `produto_para_numpy`); nenhum outro arquivo usava os nomes antigos (busca no repositório inteiro).
3. Câmera e seleção do Python marcadas como congeladas, com a regra escrita no próprio arquivo.
4. Sem mudança de comportamento: no C++ só mudaram comentários; os dtypes são idênticos aos antigos.
5. O `try/except ImportError` do carregador põe `prototypes/` no caminho quando necessário; o filho, aberto com "spawn", herda o caminho do pai. `cubo_rhi.py` importa sem esse recurso, mas só é carregado como pacote (`__main__.py` e `medir.py` põem `prototypes/` no caminho). Aceito.
6. Os quatro testes passam. Mutações pegas: `BYTES_VERTICE` 28→32 no `cena.h`; `O_MIN` 42→46 no `cena.cpp`; `guid` S22→S24, `id_step` i4→i8 e troca de `caixa_min`/`caixa_max` no Python; fluxo A voltando a importar da S03.

## PR 123: correções exigidas

1. **A cópia mais completa do formato no C++ não é conferida.** `ponte_viewport.cpp:41-42` escreve os dois dtypes inteiros como texto (`[('pos','<f4',(3,)),...]`). Mutação: mudar ali `guid` para `S24` não quebra nenhum teste do PR. Exigido: o teste lê os dois textos do `.cpp`, monta `np.dtype(ast.literal_eval(texto))` e compara com `DTYPE_VERTICE` e `DTYPE_OBJETO` (igualdade de dtype, que inclui nomes, tipos e posições).
2. **As posições de normal e cor que a placa de vídeo usa não são conferidas.** `motor.h:192-193` diz à placa que a normal começa no byte 12 e a cor no 24. Mutações que escapam: trocar a ordem de `normal` e `cor` no Python (0 falhas); mudar 12→16 no `motor.h` (0 falhas). Resultado seria cor e sombra erradas na tela, sem erro. Exigido: o teste lê as três posições do `motor.h` (os números depois de `Float3,`/`UNormByte4,` em `setAttributes`) e compara com `DTYPE_VERTICE.fields[...][1]` de `pos`, `normal` e `cor`.
3. **Posição do GlobalId e do id no `cena.cpp` não conferidas.** `cena.cpp:69-71` lê `id_step` no byte 0 e o `guid` no byte 4 com 22 letras, com números soltos no código. Mutações que escapam: `p + 4`→`p + 8` no C++ (0 falhas); trocar a ordem de `id_step` e `guid` no Python (0 falhas). Exigido: dar nome a esses números no `cena.cpp` (por exemplo `O_ID = 0, O_GUID = 4, N_GUID = 22`, na mesma linha dos outros) e conferir no teste contra `DTYPE_OBJETO`.
4. Comentário velho: `cena.h:18` ainda diz "DTYPE_OBJETO do carregador.py"; trocar para `formato_malha.py`.

## PR 125: o que está certo

1. A foto (tamanho, data em nanossegundos, soma BLAKE2b) é tirada uma vez por carga, antes de qualquer filho, e vai a todos os filhos da mesma carga: geometria, nova tentativa isolada e caixa substituta. Isso fecha o B23 para as novas tentativas.
2. Perda da placa (`adaptador.py`, `_reabrir`): limpa a tela e faz carga nova com foto nova; não mistura versões. Conferido.
3. O filho confere antes e depois do `ifcopenshell.open`; depois de aberto, o filho só usa o modelo em memória, então a conferência depois de abrir basta.
4. Arquivo ilegível na hora da foto: `tirar` devolve `None`, a carga segue e o erro real vem do `open`. Correto.
5. B32 fechado: `str(e) or 'erro desconhecido'` dentro do texto (nos três lugares) e `_pronto.set()` em `finally`; quem espera nunca fica preso.
6. O teste do filho funciona porque o carregador usa "spawn" (`carregador.py:400`): o filho importa `foto_arquivo` sem a troca feita pelo teste e acusa a diferença. Com "fork" o teste passaria sem testar nada; fica registrado.
7. Mutações pegas pelo teste puro: tirar a conferência de data, de tamanho ou de soma.

## PR 125: correções exigidas

5. **Soma calculada em toda carga sem uso.** A soma só é usada na conferência final com `manter_arquivo=True`; os filhos conferem só tamanho e data. Mesmo assim `tirar(self.caminho)` lê o arquivo inteiro a cada carga. Num IFC de 1 GB isso é uma leitura extra inteira, e ela não pode ser cancelada: `AdaptadorCarga.cancelar` espera 5 s e depois recusa abrir outro arquivo ("a carga anterior ainda não terminou"). Exigido: `foto_arquivo.tirar(self.caminho, com_soma=self.manter_arquivo)`.
6. **Conferência final com soma sem teste.** Mutação: apagar as três linhas `trocou = ...; if trocou: raise` em `_rodar` não quebra nenhum teste. Exigido: teste com `manter_arquivo=True` em que o `tirar` do pai devolve a foto real com `soma` trocada (tamanho e data iguais, então o filho passa); confere `r.estado == "concluido"`, uma linha "não foi possível manter o arquivo aberto: o arquivo mudou durante a carga (o conteúdo mudou)" em `r.mensagens` e `car.arquivo is None`.

## Recomendado (não bloqueia)

7. Caixa substituta sem teste da foto: apagar `"foto": est["foto"]` de `_caixas` não quebra nada. Um teste com `OBIM_TESTE_MATAR_FILHO` e a foto trocada só depois da primeira chamada cobriria.
8. `tirar` poderia receber uma função de "cancelado?" e conferir entre blocos de 1 MB; só importa se a soma continuar sendo calculada no começo da carga.

## Ordem de mesclagem

Os dois PRs mexem no topo de `carregador.py` (123 troca os dtypes pelo `import` de `formato_malha`; 125 põe o `import` de `foto_arquivo` no mesmo lugar). Mesclar o 123 primeiro; depois trazer o `main` para o ramo do 125 (merge, sem reescrever história), resolver o choque mantendo os dois `import`s e rodar os testes de novo.

## Para o implementador

Arquivos permitidos. PR 123: `tests/test_formato_malha.py`, `prototypes/s04/obimcore/nucleo/cena.cpp` (só a linha das constantes e as linhas 69-71 para usar os nomes), `prototypes/s04/obimcore/nucleo/cena.h` (só o comentário da linha 18). PR 125: `prototypes/viewport_qrhi/carregador.py` (só a linha do `tirar` em `_rodar`), `tests/test_viewport_carregador.py` (só testes novos; não mudar os oráculos existentes). Depois volta para nova revisão Opus (T3).
