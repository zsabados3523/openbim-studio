# SPDX-License-Identifier: AGPL-3.0-or-later
"""Medição das metas da S05 (F0-S05-T10, critério P3).
  QT_QPA_PLATFORM=offscreen python prototypes/s05/medir_s05.py [--n-ops 1000] [--tamanho-mb 50] [--saida X.md] [--sem-bateria]
  python prototypes/s05/medir_s05.py --so-windows   (só Windows; para o CI)
Por tipo: n-ops medidas após 10 de aquecimento descartadas; gc.collect() antes e gc.disable() durante o laço cronometrado.
Também: diário (3 cargas e sincronizar, com fsync), autosave e gravar_par (3 vezes), bateria T04/T05/T07 (n-ops >= 1000)
e, no Windows, fsync/replace/link (1.000 repetições). n-ops 1000 exige --tamanho-mb >= 45 (recusado antes de gerar). Saída: 0 ok; 3 META NAO ATINGIDA; 4 GATILHO DO RUST; 1 erro (relatório parcial); 2 uso inválido.
Reusa tests/s05_t04_aux.py e scripts/gerar_modelo_grande.py. A medição oficial é do PO. Fumaça: --n-ops 20 --tamanho-mb 2."""
import argparse
import gc
import hashlib
import math
import os
import platform
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from itertools import count
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(RAIZ / d) for d in ("scripts", "tests", "app")]  # mesma ordem de antes

from gerar_modelo_grande import gerar  # noqa: E402
from openbim_app.autosave import Autosave  # noqa: E402
from openbim_app.diario import Diario, pasta_projeto  # noqa: E402
from openbim_app.gravacao_par import gravar_par  # noqa: E402
from openbim_app.lateral import Lateral  # noqa: E402
from openbim_app.sessao_modelo import SessaoModelo  # noqa: E402
from openbim_app.transacao import Historico  # noqa: E402
from s05_t04_aux import aplicar, montar  # noqa: E402

SEMENTE = 20261023
PAREDES_T02, BYTES_T02_MB = 59000, 51.45  # T02: 59.000 paredes = 51.450.115 bytes, 1.003.606 entidades
SHA_T02 = "6b3304261350000847b00518c3d6d48a36bcc04374cb4755f9f4c99fcca5cc53"
LOTE, AQUEC = 50, 10
TIPOS = ("nome", "propriedade (editar valor)", "posicao", "criar parede", "apagar parede", "apagar 50 em lote")
P3 = TIPOS[:3]  # edição pequena: é o que conta para a meta de 5 ms (P3)
CARGAS = {"pequena (~120 B)": {"texto": "nota", "n": 1}, "de posicao (~2 KB)": {"txt": "x" * 2000},
          "de criar (~14 KB)": {"txt": "x" * 14000}}
NAO_SUPORTADO = "nao suportado no Windows (como app/openbim_app/gravacao_atomica.py:181)"


def sha256(caminho):
    with open(caminho, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def estat(xs):  # ms: média, p95, máximo
    s = sorted(xs)
    return sum(s) / len(s), s[max(0, math.ceil(0.95 * len(s)) - 1)], s[-1]


def criterio(media):
    return "GATILHO DO RUST (ADR-001 sec. 9)" if media > 50 else "META NAO ATINGIDA" if media > 5 else "ok"


def cronometro(fn):  # ms
    t0 = time.perf_counter(); fn(); return (time.perf_counter() - t0) * 1000


def m(x):  # número em pt-BR, 3 casas
    return f"{x:.3f}".replace(".", ",")


def trio(xs):
    return " / ".join(m(v) for v in estat(xs))


def trio_v(v):
    return v if isinstance(v, str) else " / ".join(m(x) for x in v)


def tentar(fn, *args):  # (resultado, None) ou (None, "ERRO: ..."); o relatório parcial sai mesmo assim
    try:
        return fn(*args), None
    except Exception as e:  # noqa: BLE001 (TimeoutExpired da bateria cai aqui)
        return None, f"ERRO: {type(e).__name__}: {e}"


def paredes_de(mb):
    return PAREDES_T02 if mb == 50 else round(mb * PAREDES_T02 / BYTES_T02_MB)


def _tx(sessao, h, c, op):
    with sessao.escrever() as esc, h.transacao(esc) as t:
        aplicar(op, t.ifc, t.lado, c)


def _com(sessao, fn):  # desfazer e refazer
    with sessao.escrever() as esc:
        fn(esc)


def medir_ops(n, sessao, h, c, f):
    rng = random.Random(SEMENTE)
    N = n + AQUEC  # por tipo: as AQUEC primeiras são aquecimento (descartadas)
    paredes = [w.GlobalId for w in f.by_type("IfcWall")]
    rng.shuffle(paredes)
    apagar, lote, livres = paredes[:N], paredes[N:N + LOTE * N], paredes[N + LOTE * N:]
    _tx(sessao, h, c, ("pset_criar", livres[0], "setup"))  # alvo do pset, fora da medição
    lista = {  # operações sorteadas com semente; as paredes apagadas não são tocadas pelas outras
        "nome": [("nome", rng.choice(livres)) for _ in range(N)],
        "propriedade (editar valor)": [("pset_editar", "setup") for _ in range(N)],
        "posicao": [("mover", rng.choice(livres)) for _ in range(N)],
        "criar parede": [("parede", f"m{k}") for k in range(N)],
        "apagar parede": [("apagar", g) for g in apagar],
        "apagar 50 em lote": [("lote", lote[k * LOTE:(k + 1) * LOTE]) for k in range(N)],
    }
    medidas = {}
    for nome in TIPOS:
        ops = lista[nome]
        for op in ops[:AQUEC]:  # aquecimento: executa e descarta
            _tx(sessao, h, c, op)
            _com(sessao, h.desfazer)
            _com(sessao, h.refazer)
        gc.collect()
        gc.disable()
        try:
            tx, du, rf = [], [], []
            for op in ops[AQUEC:]:
                tx.append(cronometro(lambda: _tx(sessao, h, c, op)))
                du.append(cronometro(lambda: _com(sessao, h.desfazer)))
                rf.append(cronometro(lambda: _com(sessao, h.refazer)))
        finally:
            gc.enable()
        medidas[nome] = (tx, du, rf)
        print(f"  {nome}: {n} operações medidas", file=sys.stderr)
    return medidas


def medir_arquivos(n, ifc, sessao, h, lat, tmp, lado):
    d = Diario.abrir(lado, ifc)
    linhas = {}
    for rot, dados in CARGAS.items():
        ln = [("notas", "o1", None, dados)]
        linhas[rot] = [cronometro(lambda: d.anotar("transacao", [], ln)) for _ in range(n)]
    sync = [cronometro(d.sincronizar) for _ in range(n)]  # fsync do diário
    au = Autosave(sessao, h, lat, d, lado, ifc)
    t_auto, falhas = [], 0
    for _ in range(3):
        au.anotar("transacao", [], [("notas", "o1", None, CARGAS["pequena (~120 B)"])])  # marca sujo
        ret = []
        t_auto.append(cronometro(lambda: ret.append(au.salvar())))
        falhas += ret != [True]
    par = []
    for k in range(3):
        destino = tmp / f"gravacao{k}" / "Casa.ifc"
        destino.parent.mkdir(parents=True, exist_ok=True)
        par.append(cronometro(lambda: gravar_par(sessao, h, lat, destino, pasta_projeto(lado), lado, d.ultimo_seq)))
    d.fechar()
    return {"linhas": linhas, "sync": sync, "auto": t_auto, "falhas": falhas, "par": par}


def serie(fn, reps):  # um OSError no meio não descarta as medidas já feitas
    xs = []
    try:
        for _ in range(reps):
            xs.append(cronometro(fn))
    except OSError as e:
        if not xs:
            return f"ERRO: {e}"
        return f"parcial ({len(xs)} de {reps}; erro: {e}); média / p95 / máx {trio(xs)}"
    return estat(xs)


def medir_windows(pasta, reps=1000):  # só no Windows; no Linux devolve vazio
    if sys.platform != "win32":
        return {}
    p = Path(pasta); p.mkdir(parents=True, exist_ok=True)
    a, b, out, bloco, contador = p / "a.bin", p / "b.bin", {}, b"x" * 4096, count()

    def gravar(caminho):
        with open(caminho, "wb") as f:
            f.write(bloco)
            f.flush()
            os.fsync(f.fileno())

    def fsync_pasta():
        fd = os.open(p, os.O_RDONLY)  # no Windows dá PermissionError
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def troca():
        gravar(b)
        os.replace(b, a)

    def link():
        nome = p / f"l{next(contador)}.bin"
        os.link(a, nome)
        os.remove(nome)

    try:
        gravar(a)
    except OSError as e:
        return {"gravar inicial": f"ERRO: {e}"}
    try:
        fsync_pasta()
        out["fsync da pasta"] = serie(fsync_pasta, reps)
    except PermissionError:
        out["fsync da pasta"] = NAO_SUPORTADO
    for rotulo, fn in (("fsync do arquivo (4 KB)", lambda: gravar(a)), ("troca por os.replace (4 KB)", troca),
                       ("criacao de link (os.link)", link)):
        out[rotulo] = serie(fn, reps)
    return out


def linhas_win(win):
    return [f"| Windows: {r} | {trio_v(v)} | informativo |" for r, v in win.items()]


def bateria():
    arqs = [str(p) for pre in ("test_s05_t04", "test_s05_t05", "test_s05_t07") for p in sorted((RAIZ / "tests").glob(pre + "*.py"))]
    env = dict(os.environ, OBIM_S05_OBRIGATORIO="1")  # sem módulo, vira falha (não pula)
    t0 = time.perf_counter()
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *arqs], cwd=RAIZ, env=env,
                       capture_output=True, text=True, timeout=7200)  # TimeoutExpired vira linha de erro
    seg = time.perf_counter() - t0
    fim = ([x for x in (r.stdout + r.stderr).splitlines() if re.search(r"\d+ (passed|failed|errors?|skipped|xfailed)", x)] or [""])[-1]
    cont = {k: int(g[1]) for k, rx in (("passed", "passed"), ("failed", "failed"), ("errors", "errors?"), ("skipped", "skipped"), ("xfailed", "xfailed"), ("xpassed", "xpassed")) if (g := re.search(rf"(\d+) {rx}\b", fim))}
    return len(arqs), cont, seg, r.returncode


def relatorio(a, info, medidas, arq_r, win_r, bat_r, descartados):
    (arq, err_arq), (win, err_win), (bat, err_bat) = arq_r, win_r, bat_r
    pior = max(P3, key=lambda k: estat(medidas[k][0])[0])
    media_pior = estat(medidas[pior][0])[0]
    igual = "igual ao T02" if info["sha"] == SHA_T02 else "diferente do T02; tamanho ou gerador mudou"
    L = ["# Medição S05 (F0-S05-T10)", "",
         f"Modelo: {info['paredes']} paredes, {info['entidades']} entidades apos montar, {info['bytes'] / 1e6:.2f} MB, sha256 `{info['sha']}` ({igual})",
         f"Operações por tipo: {a.n_ops} medidas, mais {AQUEC} de aquecimento descartadas por tipo; máquina: {platform.system()} {platform.release()}, Python {sys.version.split()[0]}",
         "Coletor de lixo: gc.collect() antes de cada tipo; gc.disable() durante o laço cronometrado de cada tipo, reabilitado depois.", "",
         "## Metas", "", "| Meta | Limite | Medido (ms) | Status |", "| --- | --- | --- | --- |",
         f"| Aplicar 1 operação pequena (P3: nome, propriedade, posicao), média | 5 ms | pior: {pior}, média / p95 / máx {trio(medidas[pior][0])} | {criterio(media_pior)} |",
         f"| Desfazer e refazer de uma operação (P3, pior), média | informativo | desfazer {m(estat(medidas[pior][1])[0])}; refazer {m(estat(medidas[pior][2])[0])} | ok |",
         "", "## Operações (cada uma numa transação, com registro do desfazer; ms)", "",
         "| Operação | Transação média / p95 / máx | Desfazer média / p95 / máx | Refazer média / p95 / máx | Papel | Status (média) |",
         "| --- | --- | --- | --- | --- | --- |"]
    for nome in TIPOS:
        tx, du, rf = medidas[nome]
        papel = "P3 (conta para a meta)" if nome in P3 else "informativo (fora da P3)"
        status = criterio(estat(tx)[0]) if nome in P3 else "informativo (nao conta para a meta)"
        L.append(f"| {nome} | {trio(tx)} | {trio(du)} | {trio(rf)} | {papel} | {status} |")
    L += ["", "## Outras medidas", "", "| Item | Medido (ms) | Status / nota |", "| --- | --- | --- |"]
    if arq is None:
        L.append(f"| Diário, autosave e gravar_par | {err_arq} | relatório parcial |")
    else:
        for rot, xs in arq["linhas"].items():
            L.append(f"| Diário: anotar linha {rot}, média / p95 / máx ({len(xs)} vezes) | {trio(xs)} | à parte (P3), fora da meta; sem fsync por linha (temporizador de 2 s) |")
        L.append(f"| Diário: sincronizar() com fsync, média / p95 / máx ({len(arq['sync'])} vezes) | {trio(arq['sync'])} | informativo |")
        L.append(f"| Autosave.salvar (modelo inteiro), média / p95 / máx (3 vezes) | {trio(arq['auto'])} | informativo; salvar devolveu False em {arq['falhas']} de 3 |")
        L.append(f"| gravar_par (par inteiro), média / p95 / máx (3 vezes) | {trio(arq['par'])} | informativo |")
    L.append(f"| Passos descartados pelo limite de 256 MB do desfazer (ADR-002 §4.6) | {descartados} | esperado: o lote de 1.000 estoura o limite; ok se 0 ou esperado |")
    ruim = False
    if err_bat:
        L.append(f"| Bateria T04/T05/T07 | {err_bat} | erro |")
    elif bat is None:
        L.append("| Bateria T04/T05/T07 | não rodada | fumaça (n-ops < 1000) ou --sem-bateria |")
    else:
        n_arq, cont, seg, rc = bat
        ruim = cont.get("failed", 0) + cont.get("errors", 0) > 0 or rc != 0
        resumo = ", ".join(f"{v} {k}" for k, v in cont.items()) or f"código {rc}"
        L.append(f"| Bateria T04/T05/T07 ({n_arq} arquivos): {resumo}; tempo {m(seg)} s | {m(seg * 1000)} | {'META NAO ATINGIDA' if ruim else 'ok'} |")
    if err_win:
        L.append(f"| Windows | {err_win} | erro |")
    elif win:
        L += linhas_win(win)
    else:
        L.append("| Windows: fsync do arquivo e da pasta, os.replace, os.link | n/d | medido só no Windows (CI ou PO) |")
    codigo = 4 if media_pior > 50 else 3 if (media_pior > 5 or ruim) else 1 if any((err_arq, err_win, err_bat)) else 0
    return "\n".join(L), codigo


def executar(a, tmp):
    paredes = paredes_de(a.tamanho_mb)
    ifc = tmp / "modelo.ifc"
    gerar(str(ifc), paredes=paredes)
    f, c, _ = montar(str(ifc))
    info = {"paredes": paredes, "entidades": sum(1 for _ in f), "bytes": ifc.stat().st_size, "sha": sha256(ifc)}
    sessao, lat = SessaoModelo(f), Lateral()
    h = Historico(sessao, lat)  # limite de 256 MB (ADR-002 §4.6), sem diário nesta parte
    medidas = medir_ops(a.n_ops, sessao, h, c, f)
    arq_r = tentar(medir_arquivos, a.n_ops, ifc, sessao, h, lat, tmp, "medicao-s05")
    win_r = tentar(medir_windows, tmp / "win")
    bat_r = (None, None) if (a.sem_bateria or a.n_ops < 1000) else tentar(bateria)
    return relatorio(a, info, medidas, arq_r, win_r, bat_r, h.descartados)


def so_windows(tmp):
    if sys.platform != "win32":
        return "Não é Windows: --so-windows só roda no Windows (CI). Nada medido.", 0
    win, err = tentar(medir_windows, tmp / "win")
    if err:
        return f"| Windows | {err} | erro |", 1
    return "\n".join(["| Item | Medido (ms) | Status / nota |", "| --- | --- | --- |", *linhas_win(win)]), int(any(isinstance(v, str) and v.startswith(("ERRO", "parcial")) for v in win.values()))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n-ops", type=int, default=1000, help="operações por tipo (padrão 1000; exige --tamanho-mb >= 45)")
    ap.add_argument("--tamanho-mb", type=float, default=50.0, help="tamanho aproximado do modelo sintético em MB (padrão 50)")
    ap.add_argument("--saida", help="grava a tabela markdown neste caminho")
    ap.add_argument("--sem-bateria", action="store_true", help="não roda a bateria dos oráculos")
    ap.add_argument("--so-windows", action="store_true", help="só o bloco Windows (fsync, os.replace, os.link, 1.000 repetições); fora do Windows não mede")
    a = ap.parse_args()
    if a.n_ops < 1 or a.tamanho_mb <= 0:
        ap.error("--n-ops e --tamanho-mb devem ser > 0")
    precisa = (LOTE + 1) * (a.n_ops + AQUEC) + 1  # paredes para o lote e o sorteio
    if not a.so_windows and paredes_de(a.tamanho_mb) < precisa:
        ap.error(f"--n-ops {a.n_ops} exige --tamanho-mb >= {math.ceil(precisa * BYTES_T02_MB / PAREDES_T02)} MB ({precisa} paredes; com 1000 operações o mínimo é 45 MB)")
    tmp = Path(tempfile.mkdtemp(prefix="s05_medir_"))
    os.environ["OBIM_PASTA_LOCAL"] = str(tmp / "pasta_local")  # o diário e o autosave não vão à pasta do PO
    try:
        texto, codigo = so_windows(tmp) if a.so_windows else executar(a, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(texto)
    if a.saida:
        Path(a.saida).write_text(texto + "\n", encoding="utf-8")
    sys.exit(codigo)


if __name__ == "__main__":
    main()
