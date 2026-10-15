# Revisão Opus: F0-RG-11 parte 2 (mensagens ao abrir arquivo, PR 109)

- Data: 2026-10-15
- PR: #109, ramo do PR em `dd67695`
- Cartão: F0-RG-11 em `docs/state/reports/F0-REVISAO-GERAL-2026-10-15.md` (achado B20); registro de erros do PR 102
- Revisor: Opus (não escreveu nada desta tarefa)
- Diff revisado: `app/openbim_app/ifc_summary.py` (+45 −2), `tests/test_registro.py` (+82 −2)
- `v2/` e `CLAUDE.md`: não mudam neste PR (conferido no diff contra `main`).
- CI: ainda rodando quando a revisão foi feita; o veredito abaixo não depende dele.
- Como foi conferido: leitura do diff e de `main_window.py`/`registro.py`; os testes novos rodados fora do CI com um `ifcopenshell` falso (10 passam) e 9 mutações do código para ver se algum teste quebra (7 de 9 pegas; as 2 que escapam viram as correções 1 e 2).

## Veredito: REPROVADO

O código está certo. O teste do caso principal (arquivo travado no Windows) não protege o que diz proteger.

## O que está certo

1. Ler 1 byte com o Python antes do IfcOpenShell separa bem "não consegui ler o arquivo" de "não é IFC". No Windows, arquivo travado falha já na abertura (código 32/33), e arquivo só na nuvem falha na leitura; os dois caem no `except OSError`.
2. A ordem das checagens em `_erro_do_sistema` está correta para o Windows real: o código 32/33 é olhado antes de `PermissionError` (o Python transforma o 32 em `PermissionError`).
3. Falta de memória tem mensagem própria ao abrir e ao ler; erro depois de abrir (`by_type`) não escapa mais sem aviso (achado B20, 2ª parte).
4. Nenhum erro some calado: leitura recusada vai ao registro como aviso; IFC inválido, falta de memória e erro ao ler vão com a pilha (`log.exception`). O logger `openbim.ifc` é filho de `openbim`, então cai no arquivo do PR 102.
5. A janela mostra o texto da exceção (`main_window.py:86-89`); nenhuma mudança necessária ali.
6. Os testes de memória, de erro depois de abrir, de IFC inválido no registro e o de arquivo travado (contra "não é IFC válido") falham quando o comportamento é tirado (mutações conferidas).

## Correções exigidas

1. **O arquivo travado falso não é um `PermissionError`, mas no Windows o real é.** `_Fake(32)` herda de `OSError`. Mutação conferida: pôr o teste `isinstance(exc, PermissionError)` antes do código 32/33 faz o usuário com arquivo aberto no Excel ou em outro programa ver "sem permissão", e **todos os testes continuam passando**. Correção: o falso de 32 e 33 deve herdar de `PermissionError` (ex.: `class _FakeTravado(PermissionError)` com `winerror`), nos dois testes que usam 32/33. O falso de nuvem (389) pode continuar `OSError` (o Python não converte esses códigos).
2. **A causa da leitura recusada não é conferida no registro.** Mutação conferida: apagar o `log.warning("Leitura recusada: ...")` não quebra nenhum teste, e esse é o caso novo principal do PR. Correção: em `test_arquivo_travado_e_diferente_de_ifc_invalido`, chamar `registro.iniciar()` e conferir `"Leitura recusada" in _texto_log()`.

## Recomendado (pode ir no mesmo envio; não bloqueia)

3. Teste de verdade no Windows: com `ctypes`, abrir o arquivo com `CreateFileW` e compartilhamento zero, chamar `count_by_class` e conferir "aberto em outro programa"; `skipif(sys.platform != "win32")`. Prova a mensagem com o erro real do sistema, sem falso.
4. A faixa 358 a 395 é aproximada: inclui pelo menos um código que não é de nuvem (367, processo filho bloqueado) e deixa de fora o tempo esgotado ao baixar da nuvem (426), comum sem internet. Esse caso hoje cai na mensagem geral ("o sistema recusou o acesso"), que não engana. Conferir a lista na documentação pública da Microsoft e trocar a faixa por um conjunto explícito.
5. No Windows, abrir uma pasta dá `PermissionError` (não `IsADirectoryError`), então uma pasta chamada `x.ifc` mostraria "sem permissão". Caso raro; opcional.

## Para o implementador

Arquivos permitidos: `tests/test_registro.py` (só os testes novos do RG-11 parte 2) e, se fizer o item 4, `app/openbim_app/ifc_summary.py`. Depois das correções, volta para nova revisão Opus (T3).
