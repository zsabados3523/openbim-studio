# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sonda de memória da F0-S04-T21: onde vai a memória ao abrir um IFC grande. Só mede; não altera o carregador nem o processo de malhas.
Comandos (uma configuração por execução, porque o pico é por processo; saídas só fora do repositório):
  rodar   ARQ --fios N --bloco N --saida r.json   roda `medir.medir` (mesma conta do T18) com amostrador de /proc e marcas de fase
  pecas   ARQ --saida p.json [--so-rank K]        1 fio, peça a peça: quanto cada peça faz o pico do processo crescer (classe, triângulos, MB)
  resumir PASTA [--pecas p.json]                  tabelas em Markdown (só números) a partir dos arquivos de `rodar`
Rodar sob tela virtual (xvfb-run) e, com o arquivo pesado, sob `flock` (a máquina é dividida). Nada de nome, GUID ou id de peça é impresso."""
import argparse
import json
import os
import statistics as est
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
CAMPOS = ("VmRSS", "RssAnon", "RssFile", "VmSwap", "VmHWM")  # residente, anônima (a privada do filho), arquivo, troca, pico


def _mb(kb):
    return int(kb) // 1024


def _status(pid):
    try:
        with open(f"/proc/{pid}/status") as a:
            d = {k: int(v.split()[0]) for k, v in (ln.split(":", 1) for ln in a) if k in CAMPOS}
        return [_mb(d.get(c, 0)) for c in CAMPOS]
    except (OSError, ValueError):
        return None


def _privada(pid):
    try:
        with open(f"/proc/{pid}/smaps_rollup") as a:
            return _mb(sum(int(ln.split()[1]) for ln in a if ln.startswith(("Private_Clean", "Private_Dirty"))))
    except (OSError, ValueError):
        return None


def _descendentes(eu):
    """Filhos (e netos) vivos do processo, sem o resource_tracker. Só olha ppid; nunca guarda a linha de comando."""
    pais = {}
    for d in os.listdir("/proc"):
        if d.isdigit():
            try:
                with open(f"/proc/{d}/stat") as a:
                    pais[int(d)] = int(a.read().rsplit(")", 1)[1].split()[1])
            except (OSError, ValueError, IndexError):
                pass
    achados, fila = [], [eu]
    while fila:
        p = fila.pop()
        for q, pp in pais.items():
            if pp == p:
                try:
                    with open(f"/proc/{q}/cmdline", "rb") as a:
                        ferramenta = b"resource_tracker" in a.read()
                except OSError:
                    continue
                if not ferramenta:
                    achados.append(q)
                    fila.append(q)
    return achados


class Amostrador(threading.Thread):
    """10 vezes por segundo: [residente, anônima, arquivo, troca, pico] em MB do pai e de cada filho; a privada (smaps) 1 vez por segundo."""
    def __init__(self, t0, hz=10):
        super().__init__(daemon=True)
        self.t0, self.hz, self.amostras, self.parar, self.papeis = t0, hz, [], threading.Event(), {}

    def run(self):
        eu, filhos, n = os.getpid(), [], 0
        while not self.parar.is_set():
            t = time.perf_counter() - self.t0
            if n % 5 == 0:
                filhos = _descendentes(eu)
            linha = {"t": round(t, 2)}
            for pid in [eu] + sorted(filhos):
                v = _status(pid)
                if v is not None:
                    papel = "pai" if pid == eu else self.papeis.setdefault(pid, f"f{len(self.papeis) + 1}")
                    linha[papel] = v + ([_privada(pid)] if n % 10 == 0 else [None])
            self.amostras.append(linha)
            n += 1
            self.parar.wait(max(0.0, 1.0 / self.hz - (time.perf_counter() - self.t0 - t)))


def _memoria_sistema():
    d = {}
    with open("/proc/meminfo") as a:
        for ln in a:
            k, v = ln.split(":", 1)
            if k in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                d[k] = _mb(v.split()[0])
    return d


def _saida_fora_do_repositorio(caminho):
    p = Path(caminho).resolve()
    if RAIZ in p.parents:
        raise SystemExit("a saída da sonda tem de ficar fora do repositório")
    return p


def rodar(a):
    saida = _saida_fora_do_repositorio(a.saida)
    import viewport_qrhi.medir as medir
    from viewport_qrhi.carregador import CarregadorMalhas
    marcas, t0 = [], time.perf_counter()

    class Marcado(CarregadorMalhas):  # só anota hora e tamanho; não guarda `dados` (nomes e GUIDs vêm em outras mensagens)
        _ult = 0.0

        def _tratar(self, tipo, dados, est_):
            t = round(time.perf_counter() - t0, 2)
            if tipo == "feitos":
                self._ult = t
            elif tipo == "fase":
                marcas.append((t, "fase", str(dados), self._ult))
            elif tipo == "lote":
                marcas.append((t, "lote", int(dados.vertices.nbytes + dados.indices.nbytes)))
            elif tipo in ("inicio", "fim"):
                marcas.append((t, tipo, None, self._ult))
            return super()._tratar(tipo, dados, est_)

    medir.CarregadorMalhas = Marcado
    antes = _memoria_sistema()
    am = Amostrador(t0)
    am.start()
    r = medir.medir(a.arquivo, a.fios, a.bloco)
    time.sleep(0.5)
    am.parar.set()
    am.join()
    r["simplificadas"].pop("lista", None)  # contém nomes de peças
    soma = lambda i: max(sum(v[i] for k, v in s.items() if k != "t") for s in am.amostras)  # noqa: E731
    picos = {}
    for s in am.amostras:
        for k, v in s.items():
            if k != "t":
                picos[k] = max(picos.get(k, 0), v[4])
    r.update({"soma_rss_amostrada_max_mb": soma(0), "soma_anon_amostrada_max_mb": soma(1), "pico_hwm_por_processo_mb": picos,
              "amostragem_hz": am.hz, "sistema_antes": antes, "sistema_depois": _memoria_sistema(), "marcas": marcas,
              "amostras": am.amostras, "fios": a.fios})
    saida.write_text(json.dumps(r))
    print(json.dumps({k: r[k] for k in ("fios", "bloco", "abrir_s", "pico_pai_mb", "pico_filho_mb", "pico_somado_mb",
                                         "soma_amostrada_max_mb", "soma_rss_amostrada_max_mb", "filhos_sobrando")}))


def _zerar_pico():  # VmHWM passa a valer o residente de agora
    with open("/proc/self/clear_refs", "w") as a:
        a.write("5")


def _rss_hwm():
    v = _status(os.getpid())
    return v[0], v[4]


def pecas(a):
    """1 fio, blocos como no filho. Para cada peça: crescimento do pico = maior pico do processo ao calcular e converter a peça
    (initialize()/next() calculam a peça que o get() seguinte devolve) menos o residente de antes. Não guarda ids no que imprime."""
    saida = _saida_fora_do_repositorio(a.saida)
    import ifcopenshell
    import ifcopenshell.geom
    from viewport_qrhi.carregador import CarregadorMalhas, paleta_da_peca, produto_para_numpy
    ref = CarregadorMalhas(a.arquivo)
    cfg = ifcopenshell.geom.settings()
    cfg.set("use-world-coords", True)
    cfg.set("weld-vertices", False)
    arq = ifcopenshell.open(a.arquivo)
    prods = sorted((p for p in arq.by_type("IfcProduct") if p.Representation is not None
                    and not any(p.is_a(c) for c in ref.excluir)), key=lambda p: p.id())
    if a.so_rank:
        prods = [p for p in prods if p.id() == json.loads(Path(a.ids_de).read_text())[a.so_rank - 1]]
    linhas = []  # (id, classe, triângulos, crescimento MB, pico MB, segundos)
    for ini in range(0, len(prods), 1000):
        it = ifcopenshell.geom.iterator(cfg, arq, 1, include=prods[ini:ini + 1000], geometry_library=ref.biblioteca)
        base, _ = _rss_hwm()
        _zerar_pico()
        t = time.perf_counter()
        ok = it.initialize()
        pico_c, seg_c = _rss_hwm()[1], time.perf_counter() - t
        while ok:
            s = it.get()
            _zerar_pico()
            t = time.perf_counter()
            r = produto_para_numpy(s.geometry, paleta_da_peca(s.geometry))
            pico = max(pico_c, _rss_hwm()[1])
            if r is not None:
                linhas.append((s.id, arq.by_id(s.id).is_a(), len(r[3]) // 3, pico - base, pico, round(seg_c + time.perf_counter() - t, 3)))
            del r
            base, _ = _rss_hwm()
            _zerar_pico()
            t = time.perf_counter()
            ok = it.next()
            pico_c, seg_c = _rss_hwm()[1], time.perf_counter() - t
        del it
    linhas.sort(key=lambda x: -x[3])
    classes = {}
    for _, c, tri, inc, _, _ in linhas:
        q = classes.setdefault(c, [0, 0, 0])
        q[0], q[1], q[2] = q[0] + 1, q[1] + tri, max(q[2], inc)
    saida.write_text(json.dumps({"pecas": len(linhas), "triangulos": sum(x[2] for x in linhas), "por_classe": classes,
                                 "top_crescimento": [x[1:] for x in linhas[:30]],
                                 "top_triangulos": [x[1:] for x in sorted(linhas, key=lambda x: -x[2])[:30]]}))
    if not a.so_rank:
        Path(str(saida) + ".ids").write_text(json.dumps([x[0] for x in linhas[:10]]))  # só para repetir uma peça sozinha
    print(json.dumps({"pecas": len(linhas), "maior_crescimento_mb": linhas[0][3] if linhas else None}))


def _em(am, papel, i, t):  # último valor do campo i do processo no instante t
    v = [s[papel][i] for s in am if s["t"] <= t and papel in s and s[papel][i] is not None]
    return v[-1] if v else 0


def _maximo(am, papel, i, t0, t1):
    v = [s[papel][i] for s in am if t0 <= s["t"] <= t1 and papel in s and s[papel][i] is not None]
    return max(v) if v else 0


def resumir(a):
    runs = [json.loads(p.read_text()) for p in sorted(Path(a.pasta).glob("r_*.json"))]
    g = {}
    for r in runs:
        g.setdefault((r["fios"], r["bloco"]), []).append(r)
    print("| fios | bloco | rodadas | abrir s (mediana / pior) | pico somado MB (mediana / pior) | soma amostrada máx MB (mediana / pior) | pai pico MB | filho pico MB |\n|---|---|---|---|---|---|---|---|")
    for (f, b), rs in sorted(g.items()):
        m = lambda k: f"{est.median(r[k] for r in rs):.0f} / {max(r[k] for r in rs):.0f}"  # noqa: E731
        print(f"| {f} | {b} | {len(rs)} | {est.median(r['abrir_s'] for r in rs):.1f} / {max(r['abrir_s'] for r in rs):.1f} | {m('pico_somado_mb')} | "
              f"{m('soma_rss_amostrada_max_mb')} | {est.median(r['pico_pai_mb'] for r in rs):.0f} | {est.median(r['pico_filho_mb'] for r in rs):.0f} |")
    ref = [r for r in runs if (r["fios"], r["bloco"]) == (a.fios, a.bloco)]
    if ref:
        r = sorted(ref, key=lambda x: x["pico_somado_mb"])[len(ref) // 2]  # a rodada mediana
        am, mk = r["amostras"], r["marcas"]
        fases = [m for m in mk if m[1] == "fase"]
        t_ab = next(m[0] for m in fases if m[2] == "abrindo")
        t_li = next(m[0] for m in fases if m[2] == "listando")
        conv = [m for m in fases if m[2] == "convertendo"]
        t_fim = next(m[0] for m in mk if m[1] == "fim")
        t_morte = max(s["t"] for s in am if "f1" in s)
        ult_fim = next(m[3] for m in mk if m[1] == "fim")
        ini = [m[0] for m in conv] + [t_fim]
        fim_calc = [m[3] for m in conv[1:]] + [ult_fim]
        print(f"\nRodada mediana ({a.fios} fios, bloco {a.bloco}); filho: residente / anônima (privada) em MB; amostragem {r['amostragem_hz']} Hz\n")
        print("| fase | de s | até s | duração (soma) s | filho residente máx | filho anônima máx | pai residente máx |\n|---|---|---|---|---|---|---|")
        calc = [(ini[k], fim_calc[k]) for k in range(len(conv))]  # calcular: do começo do bloco até a última peça pronta
        envio = [(fim_calc[k], ini[k + 1]) for k in range(len(conv))]  # enviar: da última peça pronta até o bloco seguinte
        for nome, trechos in (("ler o arquivo", [(t_ab, t_li)]), ("percorrer as peças", [(t_li, ini[0])]),
                              ("calcular a malha (soma dos blocos)", calc), ("enviar ao pai (soma dos blocos)", envio),
                              ("liberar (fim até o filho sumir)", [(t_fim, t_morte)])):
            mx = lambda papel, i: max(_maximo(am, papel, i, x, y) for x, y in trechos)  # noqa: E731
            print(f"| {nome} | {trechos[0][0]:.1f} | {trechos[-1][1]:.1f} | {sum(max(0.0, y - x) for x, y in trechos):.1f} | "
                  f"{mx('f1', 0)} | {mx('f1', 1)} | {mx('pai', 0)} |")
        print("\n| bloco | calcular s | enviar s | anônima ao começar | anônima máx do bloco (calcular + enviar) | instante do máx s | acima da base (após abrir) ao começar o seguinte | enviado ao pai MB |\n|---|---|---|---|---|---|---|---|")
        base = _em(am, "f1", 1, ini[0])  # anônima do filho depois de abrir e listar
        for k in range(len(conv)):
            ini_k, nxt = ini[k], ini[k + 1]
            env = sum(m[2] for m in mk if m[1] == "lote" and fim_calc[k] <= m[0] <= nxt) / 2**20
            sub = [s for s in am if ini_k <= s["t"] <= nxt and "f1" in s]
            pico = max(sub, key=lambda s: s["f1"][1]) if sub else {"t": ini_k, "f1": [0, 0]}
            print(f"| {k + 1} | {fim_calc[k] - ini_k:.1f} | {nxt - fim_calc[k]:.1f} | {_em(am, 'f1', 1, ini_k)} | {pico['f1'][1]} | {pico['t']:.1f} | {_em(am, 'f1', 1, nxt - 0.1) - base} | {env:.0f} |")
        print("\n| t s | pai residente | pai anônima | filho residente | filho anônima | filho privada (1 Hz) | soma residente |\n|---|---|---|---|---|---|---|")
        passo = max(1.0, round(t_morte / 20))
        for s in am[::max(1, int(passo * r["amostragem_hz"]))]:
            p, f = s.get("pai", [0] * 6), s.get("f1", [0] * 6)
            print(f"| {s['t']:.0f} | {p[0]} | {p[1]} | {f[0]} | {f[1]} | {f[5] if f[5] is not None else ''} | {p[0] + f[0]} |")
    if a.pecas:
        p = json.loads(Path(a.pecas).read_text())
        print(f"\nPeças com malha: {p['pecas']}; triângulos: {p['triangulos']}\n\n| # | classe IFC | triângulos | crescimento do pico no passe MB | crescimento sozinha (processo novo) MB | segundos sozinha |\n|---|---|---|---|---|---|")
        for k, (c, tri, inc, pico, seg) in enumerate(p["top_crescimento"][:10], 1):
            f = Path(a.pecas).with_name(f"pecas_so{k}.json")
            so = json.loads(f.read_text())["top_crescimento"][0] if f.exists() else None
            print(f"| {k} | {c} | {tri} | {inc} | {so[2] if so else ''} | {so[4] if so else ''} |")
        print("\n| classe IFC | peças | triângulos | maior crescimento MB |\n|---|---|---|---|")
        for c, (n, tri, inc) in sorted(p["por_classe"].items(), key=lambda x: -x[1][2])[:10]:
            print(f"| {c} | {n} | {tri} | {inc} |")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r_ = sub.add_parser("rodar")
    r_.add_argument("arquivo")
    r_.add_argument("--fios", type=int, default=8)
    r_.add_argument("--bloco", type=int, default=1000)
    r_.add_argument("--saida", required=True)
    p_ = sub.add_parser("pecas")
    p_.add_argument("arquivo")
    p_.add_argument("--saida", required=True)
    p_.add_argument("--so-rank", type=int, default=0)
    p_.add_argument("--ids-de", default=None)
    s_ = sub.add_parser("resumir")
    s_.add_argument("pasta")
    s_.add_argument("--pecas", default=None)
    s_.add_argument("--fios", type=int, default=8)
    s_.add_argument("--bloco", type=int, default=1000)
    a_ = ap.parse_args()
    {"rodar": rodar, "pecas": pecas, "resumir": resumir}[a_.cmd](a_)
