# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sonda da F0-S04-T33: ensaio da regra R-A (T29) ao abrir um IFC, em tela virtual. Só lê números; não muda o produto nem nenhum limite.
Uma abertura por execução (o pico de memória é por processo). Grava JSON só com números (nunca nome, GUID, id de peça, texto de mensagem).
Uso: sonda_ensaio_t33.py rodar ARQ.ifc --saida r.json [--fios 8] [--bloco 250] [--rotulo R] [--bloco-alvo 22]
     sonda_ensaio_t33.py --auto-teste     (lógica dos critérios de parada com números inventados; sem tela, sem IFC)
Campos ausentes saem como null. `parada.<nome>`: true = o critério do lote 60/61 passou, false = reprovou, null = sem dado para julgar.
Rodar com `rodar_t33.sh` (cadeado + tela virtual). A saída tem de ficar fora do repositório."""
import argparse
import json
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[2]
for p in (AQUI.parents[1] / "viewport_qrhi", AQUI.parents[1]):
    sys.path.insert(0, str(p))

BLOCO_ALVO = 22  # bloco das 3 peças pesadas do arquivo pesado (lote 60 §7)
LIM_ATRASO_S, LIM_SILENCIO_S, LIM_CRESC_MB, LIM_BASE_MB = 0.5, 20.0, 500.0, 50.0  # critérios de parada do lote 60/61; só são lidos
G_MB, TETO_MB = 1000.0, 6000.0  # os do produto (G_CRESCIMENTO_MB e o teto); a sonda só os lê, nunca os muda
CAMPOS = ("rotulo", "fios", "bloco", "estado", "blocos", "registro_reinicio", "reinicios", "filhos", "pico_filhos_mb", "tempos",
          "msgs_nao_feito", "msgs_visto_so_no_fim", "filhos_vivos_juntos", "conta_a_mb", "conta_b_mb", "pico_pai_mb", "m5_atraso_max_ms",
          "m5_atraso_p95_ms", "pecas_com_malha", "triangulos", "vertices", "sem_malha", "simplificadas", "pecas_modo_isolado", "abrir_s", "parada")
PARADAS = ("fonte_vigia_bloco_alvo", "tarde_zero", "atraso_armar_bloco_alvo_ok", "max_silencio_ok", "crescimento_ok", "primeira_vs_base_ok",
            "base_vs_pos_emitir_ok", "pos_emitir_vs_fim_ok")
INFORMATIVAS = ("base_vs_fim_ok",)  # (d) do lote 63: calculada e gravada, mas não para o ensaio (lote 65 §4)


def _nums(itens, chave):
    return [x[chave] for x in itens if isinstance(x, dict) and x.get(chave) is not None]


def _topo(bloco):
    return bloco["max_mb"] if bloco.get("max_mb") is not None else bloco.get("fim_mb")


def calcular_parada(r, alvo=BLOCO_ALVO):
    """Calcula os critérios de parada só do próprio JSON `r`. Não decide nada: o líder lê. None = sem dado."""
    blocos, regs = r.get("blocos") or [], r.get("registro_reinicio") or []
    atraso = _nums([b for b in blocos if b.get("bloco") == alvo], "atraso_armar_s")
    silencio = _nums(blocos, "max_silencio_s") + _nums(regs, "max_silencio_s")
    primeiro = {}
    for b in blocos:
        if b.get("filho") is not None and b.get("bloco") is not None:
            primeiro[b["filho"]] = min(primeiro.get(b["filho"], b["bloco"]), b["bloco"])
    cresc = [_topo(b) - b["base_mb"] for b in blocos
             if b.get("bloco") not in (alvo, primeiro.get(b.get("filho"))) and b.get("base_mb") is not None and _topo(b) is not None]
    pares = [(b["primeira_mb"], b["base_mb"]) for b in blocos if b.get("primeira_mb") is not None and b.get("base_mb") is not None]
    seguintes = [(a, b) for a in blocos for b in blocos  # N e N+1 do mesmo filho
                 if a.get("filho") == b.get("filho") and None not in (a.get("bloco"), b.get("bloco")) and b["bloco"] == a["bloco"] + 1]
    d_antigo = [(a["fim_mb"], b["base_mb"]) for a, b in seguintes if a.get("fim_mb") is not None and b.get("base_mb") is not None]
    d_novo = [(a["pos_emitir_mb"], b["base_mb"]) for a, b in seguintes if a.get("pos_emitir_mb") is not None and b.get("base_mb") is not None]
    sobra = [b["pos_emitir_mb"] - b["fim_mb"] for b in blocos if b.get("pos_emitir_mb") is not None and b.get("fim_mb") is not None]
    leituras = [b[c] for b in blocos for c in ("fim_mb", "pos_emitir_mb", "base_mb", "max_mb") if b.get(c) is not None]
    return {"fonte_vigia_bloco_alvo": any(g.get("fonte") == "vigia" and g.get("bloco") == alvo for g in regs),  # falso também quando não houve reinício
            "tarde_zero": not any(b.get("tarde") for b in blocos) and not any(g.get("decisao_tarde") for g in regs),
            "atraso_armar_bloco_alvo_ok": max(atraso) <= LIM_ATRASO_S if atraso else None,
            "max_silencio_ok": max(silencio) < LIM_SILENCIO_S if silencio else None,
            "crescimento_ok": max(cresc) <= LIM_CRESC_MB if cresc else None,
            "primeira_vs_base_ok": all(abs(p - b) <= LIM_BASE_MB for p, b in pares) if pares else None,
            "base_vs_fim_ok": all(abs(b - f) <= LIM_BASE_MB for f, b in d_antigo) if d_antigo else None,  # (d), informativa
            "base_vs_pos_emitir_ok": all(abs(b - p) <= LIM_BASE_MB for p, b in d_novo) if d_novo else None,  # (d′)
            "pos_emitir_vs_fim_ok": (all(x < G_MB for x in sobra) and all(x < TETO_MB for x in leituras)) if sobra else None}  # (e)


def montar(resumo, medido, amostras, isolado, rotulo, fios, bloco, alvo=BLOCO_ALVO):
    """Junta, por lista branca, o que vale gravar. `resumo` = ResumoCarga (ou parecido); `medido` = dict de `medir.medir`;
    `amostras` = linhas do Amostrador (cada uma tem 't', 'pai' e um papel por filho vivo); `isolado` = ids por filho aberto em modo isolado."""
    def g(campo):
        return getattr(resumo, campo, None)

    t, mens = g("tempos") or {}, g("mensagens") or []
    soma = [sum(v[0] for k, v in s.items() if k != "t") for s in amostras]
    r = {"rotulo": rotulo, "fios": fios, "bloco": bloco, "estado": g("estado"), "blocos": g("blocos"), "registro_reinicio": g("registro_reinicio"),
         "reinicios": g("reinicios"), "filhos": g("filhos"), "pico_filhos_mb": g("pico_filhos_mb"),
         "tempos": {k: t.get(k) for k in ("decisao_s", "morte_s", "perdido_s")},
         "msgs_nao_feito": sum("não feito" in m for m in mens) if resumo else None,
         "msgs_visto_so_no_fim": sum("visto só no fim" in m for m in mens) if resumo else None,
         "filhos_vivos_juntos": sum(sum(k not in ("t", "pai") for k in s) >= 2 for s in amostras) if amostras else None,
         "conta_a_mb": medido.get("pico_somado_mb"), "conta_b_mb": max(soma) if soma else None, "pico_pai_mb": medido.get("pico_pai_mb"),
         "m5_atraso_max_ms": medido.get("atraso_max_ms"), "m5_atraso_p95_ms": medido.get("atraso_p95_ms"),
         "pecas_com_malha": g("produtos_com_malha"), "triangulos": g("triangulos"), "vertices": g("vertices"),
         "sem_malha": len(resumo.sem_malha) if resumo else None, "simplificadas": len(resumo.simplificadas) if resumo else None,
         "pecas_modo_isolado": sum(isolado), "abrir_s": medido.get("abrir_s")}
    r["parada"] = calcular_parada(r, alvo)
    return {k: r.get(k) for k in CAMPOS}


def _saida_fora_do_repositorio(caminho):
    p = Path(caminho).resolve()
    if RAIZ in p.parents:
        raise SystemExit("a saída da sonda tem de ficar fora do repositório")
    return p


def rodar(a):
    saida = _saida_fora_do_repositorio(a.saida)
    import sonda_memoria as sm  # Amostrador de /proc (10 Hz), só leitura
    import viewport_qrhi.medir as medir
    from viewport_qrhi.carregador import CarregadorMalhas, ResumoCarga
    S = {"resumo": None, "isolado": []}

    class Marcado(CarregadorMalhas):  # só anota: o resumo entregue e quantas peças cada filho em modo isolado recebeu
        def obter(self, timeout=0.0):
            x = super().obter(timeout)
            if isinstance(x, ResumoCarga):
                S["resumo"] = x
            return x

        def _rodar(self, est, ids, isolado, por_peca=False):
            if isolado:
                S["isolado"].append(len(ids or []))
            return super()._rodar(est, ids, isolado, por_peca)

    medir.CarregadorMalhas = Marcado
    am = sm.Amostrador(time.perf_counter())
    am.start()
    try:
        medido = medir.medir(a.arquivo, a.fios, a.bloco)
    finally:
        time.sleep(0.5)
        am.parar.set()
        am.join()
    r = montar(S["resumo"], medido, am.amostras, S["isolado"], a.rotulo, a.fios, a.bloco, a.bloco_alvo)
    saida.write_text(json.dumps(r))
    print(json.dumps({"rotulo": a.rotulo, "estado": r["estado"], "abrir_s": r["abrir_s"], "parada": r["parada"]}))


def auto_teste():
    """Números inventados nos dois lados de cada limite; também confere que todo campo sai (null quando falta)."""
    def b(n, f=1, base=1000, mx=1100, **kw):
        return {"bloco": n, "filho": f, "base_mb": base, "max_mb": mx, "fim_mb": mx, "atraso_armar_s": 0.1, "max_silencio_s": 1.0,
                "primeira_mb": base, "tarde": False, "pos_emitir_mb": base, **kw}
    bom = {"blocos": [b(1), b(2), b(22, atraso_armar_s=0.5), b(23, f=2, base=900, mx=1400)],
           "registro_reinicio": [{"bloco": 22, "fonte": "vigia", "decisao_tarde": False, "max_silencio_s": 19.9}]}
    def criterios(r):  # só os que param o ensaio (as informativas ficam de fora)
        return {k: v for k, v in calcular_parada(r).items() if k in PARADAS}
    assert criterios(bom) == dict.fromkeys(PARADAS, True), calcular_parada(bom)
    assert calcular_parada(bom)["base_vs_fim_ok"] is False  # (d) antigo: gravado como falso e não para (fim 1100 contra base 1000)
    ruins = {"fonte_vigia_bloco_alvo": [{"registro_reinicio": [{"bloco": 22, "fonte": "gancho"}]}, {"registro_reinicio": [{"bloco": 21, "fonte": "vigia"}]}, {"registro_reinicio": []}],
             "tarde_zero": [{"blocos": [b(1, tarde=True)]}, {"registro_reinicio": [{"bloco": 22, "fonte": "vigia", "decisao_tarde": True}]}],
             "atraso_armar_bloco_alvo_ok": [{"blocos": [b(22, atraso_armar_s=0.51)]}],
             "max_silencio_ok": [{"blocos": [b(1, max_silencio_s=20.0)]}, {"registro_reinicio": [{"bloco": 22, "fonte": "vigia", "max_silencio_s": 25}]}],
             "crescimento_ok": [{"blocos": [b(1), b(2, mx=1501)]}, {"blocos": [b(1), b(3, mx=None, fim_mb=1700)]}],
             "primeira_vs_base_ok": [{"blocos": [b(1, primeira_mb=1051)]}, {"blocos": [b(1, primeira_mb=949)]}],
             "base_vs_pos_emitir_ok": [{"blocos": [b(1, pos_emitir_mb=1050.1), b(2)]}, {"blocos": [b(1, pos_emitir_mb=949.9), b(2)]}],
             "pos_emitir_vs_fim_ok": [{"blocos": [b(1, mx=1000, pos_emitir_mb=2000)]}, {"blocos": [b(1, pos_emitir_mb=1000, mx=None, fim_mb=6000)]}]}
    for nome, lista in ruins.items():
        for ruim in lista:
            assert calcular_parada({**bom, **ruim})[nome] is False, (nome, ruim)
    assert criterios({**bom, "blocos": [b(1, primeira_mb=1050), b(2, mx=1500), b(22, atraso_armar_s=0.5)]}) == dict.fromkeys(PARADAS, True)  # no limite exato passa
    assert criterios({"blocos": [b(1, pos_emitir_mb=1050), b(2)]})["base_vs_pos_emitir_ok"] is True  # (d′) = 50 passa
    assert criterios({"blocos": [b(1, mx=1000, fim_mb=1000, pos_emitir_mb=1999), b(2)]})["pos_emitir_vs_fim_ok"] is True  # (e) 999 passa
    assert criterios({"blocos": [b(1, mx=1000, fim_mb=1000, pos_emitir_mb=2000), b(2)]})["pos_emitir_vs_fim_ok"] is False  # (e) 1000 para
    assert criterios({"blocos": [b(1, base=5999, mx=5999, fim_mb=5999, pos_emitir_mb=5999)]})["pos_emitir_vs_fim_ok"] is True
    assert criterios({"blocos": [b(1, base=5999, mx=6000, fim_mb=5999, pos_emitir_mb=5999)]})["pos_emitir_vs_fim_ok"] is False  # leitura 6000 para
    assert criterios({"blocos": [b(1, pos_emitir_mb=None)]})["pos_emitir_vs_fim_ok"] is None  # sem a medida, sem julgamento
    assert calcular_parada({"blocos": [b(2, mx=2000), b(22, mx=9000)]})["crescimento_ok"] is None  # 1º bloco do filho e bloco alvo não contam
    assert criterios({}) == dict.fromkeys(PARADAS) | {"fonte_vigia_bloco_alvo": False, "tarde_zero": True}
    from types import SimpleNamespace as NS
    assert set(montar(None, {}, [], [], "x", 1, 1)) == set(CAMPOS)
    res = NS(estado="concluido", blocos=[], registro_reinicio=[], reinicios=[], filhos=1, pico_filhos_mb=[10.0], tempos={"decisao_s": 1.0},
             mensagens=["reinício pedido e não feito (bloco 3)", "x visto só no fim do bloco 4: reinício não feito (tarde)"], produtos_com_malha=5,
             triangulos=60, vertices=180, sem_malha=[1], simplificadas=[])
    j = montar(res, {"pico_somado_mb": 300, "pico_pai_mb": 100, "atraso_max_ms": 7.0}, [{"t": 0, "pai": [10], "f1": [5], "f2": [4]}, {"t": 1, "pai": [20], "f1": [5]}], [3, 4], "x", 8, 1000)
    assert (j["msgs_nao_feito"], j["msgs_visto_so_no_fim"], j["filhos_vivos_juntos"], j["conta_b_mb"], j["pecas_modo_isolado"], j["sem_malha"]) == (2, 1, 1, 25, 7, 1), j
    assert j["tempos"] == {"decisao_s": 1.0, "morte_s": None, "perdido_s": None} and j["abrir_s"] is None
    print("auto-teste ok")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto-teste", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r_ = sub.add_parser("rodar")
    r_.add_argument("arquivo")
    r_.add_argument("--saida", required=True)
    r_.add_argument("--fios", type=int, default=8)
    r_.add_argument("--bloco", type=int, default=250)
    r_.add_argument("--rotulo", default="t33")
    r_.add_argument("--bloco-alvo", type=int, default=BLOCO_ALVO)
    a_ = ap.parse_args()
    if a_.auto_teste:
        auto_teste()
    elif a_.cmd == "rodar":
        rodar(a_)
    else:
        ap.error("use --auto-teste ou o comando rodar")
