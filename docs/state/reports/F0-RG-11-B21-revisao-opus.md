# Revisão Opus: F0-RG-11, achado B21 (queda do processo de geometria, PR 113)

- Data: 2026-10-15
- PR: #113, ramo do PR em `51a8067`
- Cartão: F0-RG-11 em `docs/state/reports/F0-REVISAO-GERAL-2026-10-15.md` (achado B21)
- Revisor: Opus (não escreveu nada desta tarefa)
- Diff revisado: `prototypes/viewport_qrhi/carregador.py` (+21 −5), `prototypes/viewport_qrhi/processo_malhas.py` (+1), `tests/test_viewport_queda_registro.py` (novo, 21 linhas)
- `v2/` e `CLAUDE.md`: não mudam neste PR (conferido no diff contra `main`).
- CI: na fila quando a revisão foi feita; o veredito abaixo não depende dele.
- Como foi conferido: leitura do diff e do caminho inteiro (`_executar`, `_rodar`, `_caixas`, `_tratar`, `_Enviador`, `_bloco`). As quedas usam processo filho de verdade e o IfcOpenShell, que não estão neste ambiente; as mutações foram avaliadas lendo o caminho de cada uma até o teste.

## Veredito: REPROVADO

O código fecha os três pontos do achado B21. O teste cobre só um deles.

## O que está certo

1. Código de saída guardado: depois do fim do canal, `filho.join(2)` e então `filho.exitcode`. O valor vai ao registro e ao texto da peça simplificada ("o conversor caiu nesta peça, código de saída N") e ao erro de abertura em `_rodar`.
2. O `os._exit(3)` do bloco com várias peças agora manda uma `nota` com o tipo e o texto da exceção antes de sair. `_Enviador` manda direto pelo canal (sem fila nem thread), então a nota já está no canal quando o filho sai e o pai a lê antes do fim do canal.
3. O `except RuntimeError: pass` da caixa substituta virou aviso no registro, e o caso "o filho da caixa não terminou" (antes ignorado em silêncio) também é registrado. As peças continuam indo para `sem_malha` com motivo (regra "nada some").
4. A interface não trava: nada novo bloqueia. A única espera nova é o `join(2)` que já existia, na thread do carregador, não na da janela.
5. Logger `openbim.viewport` é filho de `openbim`: no app vai para o arquivo do PR 102.
6. O teste novo pega duas mutações: tirar o `log.warning` da queda (cai o `caplog`) e tirar o `codigo` do retorno (cai a frase mostrada ao usuário). Ele roda no CI (as guardas `requer_a`/`requer_limite` ligam com o `main` atual).

## Correções exigidas (só testes; arquivos permitidos abaixo)

1. **Saída limpa sem resultado e queda por sinal sem teste.** Hoje só o código 3 do gancho é testado. Acrescentar um teste de `_executar` com dois alvos de nível de módulo num arquivo auxiliar de teste (exigido pelo "spawn"): (a) `os._exit(0)` sem mandar `fim` → retorno `{"motivo": "queda", "codigo": 0}` e "código de saída 0" no registro; (b) `os.kill(os.getpid(), signal.SIGTERM)` → código `-15` no Linux e `15` no Windows (lá o Python chama `TerminateProcess` com 15), e o mesmo código no registro.
2. **A `nota` não tem teste.** Mutação: apagar o `enviar("nota", ...)` em `processo_malhas.py` ou o ramo `"nota"` em `_tratar` não quebra nada. Acrescentar: (a) teste de `_bloco` com um `ifcopenshell` falso cujo iterador levanta erro, `entregar` ligado, 2 peças, `enviar` que grava as mensagens e `os._exit` trocado por uma função que levanta `SystemExit`: confere que a última mensagem antes da saída é `("nota", ...)` com o texto do erro; (b) teste de `_tratar("nota", "x", est)` conferindo "Processo de geometria: x" no `caplog`.
3. **A falha da caixa substituta não tem teste.** Mutação: voltar o `except RuntimeError` para `pass` não quebra nada, e esse era o terceiro ponto do achado. Acrescentar um teste que faça o `_executar` da caixa falhar (por exemplo, envolver `CarregadorMalhas._executar` para levantar `RuntimeError` só quando o alvo for `entrada_caixa`, numa carga com `OBIM_TESTE_MATAR_FILHO`) e confira: aviso "O processo da caixa substituta falhou" no registro e a peça em `sem_malha` com motivo.

## Recomendado (não bloqueia)

4. Código de saída mais legível no registro: negativo vira "encerrado pelo sistema (sinal N)"; no Windows, número grande em hexadecimal (ex.: `0xC0000005`, acesso inválido à memória, o caso típico de queda dentro do conversor C++).
5. Na frase mostrada ao usuário, "código de saída 0" soa estranho para quem não programa; pode virar "o conversor parou sem terminar".

## Para o implementador

Arquivos permitidos: `tests/test_viewport_queda_registro.py` e um auxiliar novo em `tests/` para os alvos do item 1. Se fizer os itens 4 ou 5, também `prototypes/viewport_qrhi/carregador.py` (só `_texto_saida` e o `log.warning` da queda). Não editar `tests/test_viewport_processo.py` nem os outros oráculos. Depois volta para nova revisão Opus (T3).

---

# Segunda revisão (commit `b190350`)

## Veredito: APROVADO (a mesclagem continua dependendo do CI obrigatório verde)

Só testes mudaram (`tests/_queda_alvos.py` novo e `tests/test_viewport_queda_registro.py`); o código do carregador é o mesmo de `51a8067`.

1. **Saída limpa e queda por sinal: feito.** `sair_zero` (`os._exit(0)` sem `fim`) e `morrer_por_sinal` (`SIGTERM`: −15 no Linux, 15 no Windows) rodam por `_executar` com processo filho de verdade; o teste confere `motivo`, `codigo` e o texto no registro. Os alvos ficam num módulo de teste importável, como o "spawn" exige (o caminho do Python vai junto para o filho).
2. **Nota: feito.** `_tratar("nota", ...)` confere o registro. `_bloco` com `ifcopenshell` falso (iterador que levanta erro, 2 peças, `entregar` ligado, `os._exit` trocado por exceção) confere que a última mensagem é a nota, com o texto do erro e "2 peças", e que a saída é com código 3. Tirar o `enviar("nota", ...)` ou o ramo de `_tratar` agora quebra teste.
3. **Falha da caixa: feito.** `_executar` envolvido só quando o alvo é `pm.entrada_caixa` (mesmo objeto de módulo que o carregador usa: os dois importam `viewport_qrhi.processo_malhas`). O teste confere o aviso no registro e a peça em `sem_malha` com "não foi possível calcular a caixa". Voltar o `except` para `pass` agora quebra teste.

Os itens 4 e 5 (recomendados) ficaram de fora; continuam valendo para depois.
