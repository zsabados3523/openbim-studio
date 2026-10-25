# SPDX-License-Identifier: AGPL-3.0-or-later
"""Filho do teste do fluxo B, parte 2a (tests/test_s04_fluxo_b_paredes.py, "Parte 2a" de tools/s04/fluxo_b/CONTRATO.md), em PROCESSO À PARTE: queda ou impasse da trava
(itens 1 e 4 do lote 22) viram falha limpa do teste, sem derrubar nem travar o pytest. Uso: `localidade T N PASTA` ou `corrida K N`; imprime `RESULTADO {json}`."""
import json
import locale
import os
import sys
import threading
import time
from pathlib import Path

if os.environ.get("OBIM_S04_FLUXO_B_DIR"):
    sys.path.insert(0, os.environ["OBIM_S04_FLUXO_B_DIR"])
import fluxo_b_paredes as M  # noqa: E402
import ifcopenshell  # noqa: E402,F401  (registra os esquemas)
def modelo(n, c=4.25):  # tipo + n paredes; a 1a é mudada para 5,5 m
    b = M.Paredes()
    b.criar_tipo("PAR", [0.02, 0.11, 0.02])
    ws = b.criar_paredes_lote("PAR", c, 2.8, 0.15, n)
    return b, ws
def localidade(t, n, pasta):  # t threads gravam n modelos cada com a vírgula ligada no processo; uma sonda lê o separador decimal sem parar
    nome = next((c for c in ("pt_BR.UTF-8", "pt_BR.utf8", "Portuguese_Brazil.1252", "pt_BR") if not isinstance(_tenta(c), locale.Error)), None)
    if nome is None:
        return {"localidade": None}
    virgula = locale.localeconv()["decimal_point"] == ","
    amostras, janelas, erros, parar, largada = [], [], [], threading.Event(), threading.Barrier(t + 1)

    def sonda():
        largada.wait()
        while not parar.is_set():
            amostras.append((time.perf_counter(), locale.localeconv()["decimal_point"]))
            time.sleep(0.0002)

    def grava(k):
        try:
            largada.wait()
            for i in range(n):
                b, ws = modelo(1500)  # 1500 paredes: a gravação dura dezenas de ms, tempo para a sonda cair DENTRO dela
                b.mudar_comprimento(ws[0], 5.5)
                t0 = time.perf_counter()
                b.gravar(str(Path(pasta) / f"g_{k}_{i}.ifc"))
                janelas.append((t0, time.perf_counter()))
        except BaseException as e:  # noqa: BLE001
            erros.append(repr(e))

    ths = [threading.Thread(target=sonda)] + [threading.Thread(target=grava, args=(k,)) for k in range(t)]
    [x.start() for x in ths]
    [x.join(240) for x in ths[1:]]
    parar.set()
    ths[0].join(10)
    dentro = [d for tt, d in amostras if any(a <= tt <= z for a, z in janelas)]
    r = {"localidade": nome, "virgula_no_processo": virgula, "erros": erros, "decimal_depois": locale.localeconv()["decimal_point"], "arquivos": sorted(str(x) for x in Path(pasta).glob("g_*.ifc")),
         "sondas": {"total": len(amostras), "com_virgula": sum(d == "," for _, d in amostras), "dentro_de_gravacao": len(dentro), "dentro_com_virgula": sum(d == "," for d in dentro)}}
    locale.setlocale(locale.LC_NUMERIC, "C")
    return r
def _tenta(c):
    try:
        return locale.setlocale(locale.LC_NUMERIC, c)
    except locale.Error as e:
        return e
def corrida(k, n):  # lote de n paredes numa thread; a principal tenta um 2o escritor com espera=0 e depois lê
    ref, _ = modelo(1)  # o mesmo comando numa thread só
    ref.criar_paredes_lote("PAR", 4.25, 2.8, 0.15, n)
    it = []
    for _ in range(k):
        b, _ = modelo(1)
        antes, saida = b.contar("IfcWall"), {}
        th = threading.Thread(target=lambda: saida.update(r=b.criar_paredes_lote("PAR", 4.25, 2.8, 0.15, n)))
        t0, ocupado, livre, maior = time.perf_counter(), 0, 0, 0.0
        th.start()
        while ocupado == 0 and th.is_alive():
            t1 = time.perf_counter()
            try:
                b.editar_propriedades("0" * 22, nome="x", espera=0)  # alvo inexistente: trava livre = ValueError; ocupada = ModeloOcupado (a trava vem ANTES da validação)
            except M.ModeloOcupado:
                ocupado += 1
            except ValueError:
                livre += 1
            maior = max(maior, (time.perf_counter() - t1) * 1000)
            time.sleep(0.001)
        lido = b.contar("IfcWall")  # a leitura espera o comando em curso: nunca vê o lote pela metade
        th.join(60)
        it.append({"ocupado": ocupado, "livre": livre, "maior_tentativa_ms": maior, "lido_durante": lido, "esperado": antes + n, "retorno": len(saida.get("r", [])), "pode_desfazer": b.pode_desfazer(),
                   "total": b.contar(None), "total_ref": ref.contar(None), "paredes_final": b.contar("IfcWall")})
    return {"iteracoes": it}
def a_frio(t):  # t threads criam o PRIMEIRO `Paredes()` do processo ao mesmo tempo (largada por barreira) e já usam o modelo; nada foi construído antes na thread principal
    largada, erros, saidas = threading.Barrier(t), [], {}

    def uma(k):
        try:
            largada.wait()
            b = M.Paredes()
            b.criar_tipo("PAR", [0.02, 0.11, 0.02])  # os comandos soltam o GIL: só o construtor poderia segurá-lo
            ws = b.criar_paredes_lote("PAR", 4.25, 2.8, 0.15, 20)
            saidas[k] = (len(ws), b.contar("IfcWall"), b.pode_desfazer())
        except BaseException as e:  # noqa: BLE001
            erros.append(repr(e))

    ths = [threading.Thread(target=uma, args=(k,)) for k in range(t)]
    [x.start() for x in ths]
    [x.join(120) for x in ths]
    return {"erros": erros, "vivas": sum(x.is_alive() for x in ths), "saidas": sorted(saidas.items())}
if __name__ == "__main__":
    a = sys.argv[1:]
    print("RESULTADO " + json.dumps(a_frio(int(a[1])) if a[0] == "frio" else localidade(int(a[1]), int(a[2]), a[3]) if a[0] == "localidade" else corrida(int(a[1]), int(a[2]))))
