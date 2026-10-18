# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sonda da F0-S04-T24: testes baratos da memória ao abrir o arquivo pesado. Só mede; não altera o carregador, o processo de malhas
nem `sonda_memoria.py` (T21), de onde vêm o amostrador e as funções de /proc. Comandos (uma configuração por execução):
  rodar   ARQ --fios N --bloco N --rotulo R --saida r.json [--alvos ids.json] [--reinicios N[,N...]] [--malloc CHAVE=VALOR ...]
          roda `medir.medir` (mesma conta do T21) com marcas; grava só números. --alvos = lista de ids (fora do repositório; nunca impressa):
          dá bloco de cada peça pesada, o maior silêncio do filho por bloco e os triângulos de cada peça no carregador.
          --reinicios 5 = protótipo da opção 1-B: o 1º filho termina limpo depois de 5 blocos e o carregador abre um filho NOVO com o resto
          (pelo mesmo caminho do carregador: ids pendentes + deslocamento). --malloc: variável da glibc só para o(s) filho(s).
  resumir PASTA ROTULO[,ROTULO...] [--ref ROTULO]   tabela em Markdown (só números) de PASTA/ROTULO_r*.json
Rodar sob tela virtual (xvfb-run) e sob `flock ~/openbim-medicao/medicao.lock`. Nada de nome, GUID ou id de peça é impresso nem gravado."""
import argparse
import hashlib
import json
import os
import statistics as est
import sys
import threading
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
for p in (AQUI, AQUI.parent):
    sys.path.insert(0, str(p))
import sonda_memoria as sm  # noqa: E402  (Amostrador, _memoria_sistema, _saida_fora_do_repositorio)


def entrada_parada(tx, params):
    """Filho do protótipo 1-B: o `processo_malhas.entrada` de sempre, mas, se OBIM_T24_BLOCOS=N (N>0), termina limpo (manda `fim`)
    quando ia começar o bloco N+1, sempre numa fronteira de bloco. Nível do módulo, exigido pelo "spawn"."""
    from viewport_qrhi import processo_malhas as pm
    n = int(os.environ.get("OBIM_T24_BLOCOS", "0"))

    class Tx:
        k = 0

        def send(self, msg):
            if n and msg[0] == "fase" and msg[1] == "convertendo":
                self.k += 1
                if self.k > n:
                    tx.send(("fim", {"tempos": {}, "pico_memoria_mb": pm.pico_memoria_mb(), "mensagens": []}))
                    os._exit(0)
            tx.send(msg)
    pm.entrada(Tx(), params)


class Arenas(threading.Thread):
    """1 vez por segundo, por filho: regiões `rw-p` anônimas alinhadas em 64 MiB (heaps das arenas extras da glibc) e fios.
    Controle positivo de MALLOC_ARENA_MAX: com 1 arena não deve aparecer nenhuma."""
    def __init__(self):
        super().__init__(daemon=True)
        self.parar, self.max_arenas, self.max_fios = threading.Event(), {}, {}

    def run(self):
        while not self.parar.wait(1.0):
            for k, pid in enumerate(sorted(sm._descendentes(os.getpid()))):
                try:
                    with open(f"/proc/{pid}/maps") as a:
                        n = sum(1 for ln in a if (f := ln.split(None, 5))[1] == "rw-p" and len(f) < 6
                                and int(f[0].split("-")[0], 16) % (1 << 26) == 0)
                    with open(f"/proc/{pid}/status") as a:
                        fios = next(int(ln.split()[1]) for ln in a if ln.startswith("Threads:"))
                except (OSError, ValueError, StopIteration):
                    continue
                self.max_arenas[k] = max(self.max_arenas.get(k, 0), n)
                self.max_fios[k] = max(self.max_fios.get(k, 0), fios)


def rodar(a):
    saida = sm._saida_fora_do_repositorio(a.saida)
    import numpy as np
    import viewport_qrhi.medir as medir
    from viewport_qrhi import processo_malhas
    from viewport_qrhi.carregador import CarregadorMalhas
    alvos = {int(i): r for r, i in enumerate(json.loads(Path(a.alvos).read_text()), 1)} if a.alvos else {}
    plano = [int(x) for x in a.reinicios.split(",")] if a.reinicios else []
    t0 = time.perf_counter()
    S = {"marcas": [], "pos": {}, "gap": {}, "tri": dict.fromkeys(alvos.values(), 0), "hash": hashlib.blake2b(digest_size=16),
         "hlote": [], "msgs_lote": 0, "pico_fim": [], "chamadas": [], "ids": []}

    class Marcado(CarregadorMalhas):  # anota hora, silêncio e tamanho; não guarda `dados` (nomes e GUIDs vêm em outras mensagens)
        _prev, _fim = None, None

        def _rodar(self, est_, ids, isolado, por_peca=False):
            k = len(S["chamadas"])
            os.environ["OBIM_T24_BLOCOS"] = str(plano[k]) if k < len(plano) else "0"
            S["chamadas"].append({"ids_none": ids is None, "isolado": bool(isolado), "ini": round(time.perf_counter() - t0, 2)})
            r = super()._rodar(est_, ids, isolado, por_peca)
            S["chamadas"][-1].update(fim=round(time.perf_counter() - t0, 2), terminou_limpo=r is None)
            if plano and r is not None:
                raise RuntimeError("protótipo 1-B: um filho caiu ou passou do limite; a rodada não vale")
            return r

        def _tratar(self, tipo, dados, est_):
            t = time.perf_counter() - t0
            k = len(S["chamadas"])
            if self._fim is not None and self._fase == "convertendo":  # silêncio como o vigia vê: do fim da mensagem anterior à chegada desta
                c = f"{k}.{self._conv}"
                S["gap"][c] = max(S["gap"].get(c, 0.0), t - self._fim)
            if tipo == "fase":
                S["marcas"].append((round(t, 2), str(dados), k))
            elif tipo == "inicio" and dados["produtos"] and not S["ids"]:
                S["ids"] = [int(x[0]) for x in dados["produtos"]]  # só os ids, em ordem; nada é impresso
                S["pos"] = {i: S["ids"].index(i) for i in alvos if i in S["ids"]}
            elif tipo == "feitos" and dados in alvos:
                S.setdefault("feitos_alvo", []).append((alvos[dados], k, self._conv, round(t, 2)))
            elif tipo == "lote":
                S["msgs_lote"] += 1
                h = hashlib.blake2b(digest_size=8)
                for x in (dados.vertices, dados.indices, dados.objetos, np.asarray(dados.deslocamento)):
                    h.update(np.ascontiguousarray(x).reshape(-1).view(np.uint8))
                S["hash"].update(h.digest())
                S["hlote"].append(h.hexdigest()[:8])
                S["marcas"].append((round(t, 2), "lote", int(dados.vertices.nbytes + dados.indices.nbytes)))
                for i, r in alvos.items():
                    m = dados.objetos["id_step"] == i
                    if m.any():
                        S["tri"][r] += int(dados.objetos["n_indices"][m].sum()) // 3
            elif tipo == "fim":
                S["pico_fim"].append(round(dados["pico_memoria_mb"]))
            try:
                return super()._tratar(tipo, dados, est_)
            finally:
                self._fim = time.perf_counter() - t0

    medir.CarregadorMalhas = Marcado
    if plano:
        processo_malhas.entrada = entrada_parada
    for kv in a.malloc or []:  # depois de iniciar: vale só para os filhos (a glibc lê a variável na partida do processo)
        k, v = kv.split("=", 1)
        os.environ[k] = v
    antes = sm._memoria_sistema()
    am, ar = sm.Amostrador(t0), Arenas()
    am.start()
    ar.start()
    r = medir.medir(a.arquivo, a.fios, a.bloco)
    time.sleep(0.5)
    am.parar.set()
    ar.parar.set()
    am.join()
    r["simplificadas"].pop("lista", None)  # contém nomes de peças
    soma = lambda i: max(sum(v[i] for k, v in s.items() if k != "t") for s in am.amostras)  # noqa: E731
    picos = {}
    for s in am.amostras:
        for k, v in s.items():
            if k != "t":
                picos[k] = max(picos.get(k, 0), v[4])
    r.update({"rotulo": a.rotulo, "fios": a.fios, "malloc": a.malloc or [], "reinicios": plano, "soma_rss_amostrada_max_mb": soma(0),
              "pico_hwm_por_processo_mb": picos, "pico_fim_por_filho_mb": S["pico_fim"], "papeis_filhos": sorted(k for k in picos if k != "pai"),
              "chamadas": S["chamadas"], "lotes_do_carregador": S["msgs_lote"], "hash_fluxo": S["hash"].hexdigest(), "hash_lotes": S["hlote"],
              "silencio_max_s_por_bloco": {k: round(v, 2) for k, v in S["gap"].items()}, "posicao_alvos": S["pos"] and
              {alvos[i]: [p, p // a.bloco + 1] for i, p in S["pos"].items()}, "feitos_alvos": S.get("feitos_alvo", []),
              "triangulos_alvos": S["tri"], "arenas_max_por_filho": ar.max_arenas, "fios_max_por_filho": ar.max_fios,
              "sistema_antes": antes, "sistema_depois": sm._memoria_sistema(), "marcas": S["marcas"], "amostras": am.amostras})
    saida.write_text(json.dumps(r))
    print(json.dumps({k: r[k] for k in ("rotulo", "fios", "bloco", "abrir_s", "pico_pai_mb", "pico_filho_mb", "pico_somado_mb", "estado",
                                         "papeis_filhos", "filhos_sobrando", "lotes_do_carregador")}))


def resumir(a):
    ref = None
    print("| rótulo | rodadas | abrir s (mediana / pior) | pico somado MB (mediana / pior) | pai pico MB | filho pico MB (maior filho) | soma amostrada máx MB | filhos | simplificadas | sem malha | hash do fluxo igual ao de ref. | arenas máx (filho) |\n|---|---|---|---|---|---|---|---|---|---|---|---|")
    for rot in ([a.ref] if a.ref else []) + [x for x in a.rotulos.split(",") if x != a.ref]:
        rs = [json.loads(p.read_text()) for p in sorted(Path(a.pasta).glob(f"{rot}_r*.json"))]
        if not rs:
            continue
        ref = ref or rs[0]["hash_fluxo"]
        m = lambda k: f"{est.median(r[k] for r in rs):.0f} / {max(r[k] for r in rs):.0f}"  # noqa: E731
        print(f"| {rot} | {len(rs)} | {est.median(r['abrir_s'] for r in rs):.1f} / {max(r['abrir_s'] for r in rs):.1f} | {m('pico_somado_mb')} | "
              f"{est.median(r['pico_pai_mb'] for r in rs):.0f} | {est.median(r['pico_filho_mb'] for r in rs):.0f} | {m('soma_rss_amostrada_max_mb')} | "
              f"{sorted({len(r['papeis_filhos']) for r in rs})} | {sorted({r['simplificadas']['quantidade'] for r in rs})} | {sorted({r['pecas_sem_malha'] for r in rs})} | "
              f"{sum(r['hash_fluxo'] == ref for r in rs)}/{len(rs)} | {max(max(r['arenas_max_por_filho'].values(), default=0) for r in rs)} |")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r_ = sub.add_parser("rodar")
    r_.add_argument("arquivo")
    r_.add_argument("--fios", type=int, default=8)
    r_.add_argument("--bloco", type=int, default=1000)
    r_.add_argument("--rotulo", required=True)
    r_.add_argument("--saida", required=True)
    r_.add_argument("--alvos", default=None)
    r_.add_argument("--reinicios", default=None)
    r_.add_argument("--malloc", action="append")
    s_ = sub.add_parser("resumir")
    s_.add_argument("pasta")
    s_.add_argument("rotulos")
    s_.add_argument("--ref", default=None)
    a_ = ap.parse_args()
    {"rodar": rodar, "resumir": resumir}[a_.cmd](a_)
