# SPDX-License-Identifier: AGPL-3.0-or-later
"""Medição das metas da S05 (F0-S05-T10, critério P3). Uso:
  QT_QPA_PLATFORM=offscreen python prototypes/s05/medir_s05.py [--n-ops 1000] [--tamanho-mb 50] [--saida CAMINHO.md] [--sem-bateria]
Mede: n-ops operações de cada tipo do ADR-002 (cada uma numa transação, com registro do desfazer), desfazer e refazer de cada uma,
diário à parte, autosave, gravação do par, bateria dos oráculos T04/T05/T07 (só com n-ops >= 1000) e, no Windows, fsync/replace/link.
Reusa tests/s05_t04_aux.py (montar, aplicar) e scripts/gerar_modelo_grande.py. A medição oficial é do PO.
Fumaça: --n-ops 20 --tamanho-mb 2 (sem bateria: o critério pede n-ops >= 1000)."""
import argparse
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
for _p in (RAIZ / "app", RAIZ / "tests", RAIZ / "scripts"):
    sys.path.insert(0, str(_p))

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
LOTE = 50
TIPOS = ("nome", "propriedade (editar valor)", "posicao", "criar parede", "apagar parede", "apagar 50 em lote")
P3 = TIPOS[:3]  # edição pequena: é o que conta para a meta de 5 ms (P3)


def sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def estat(xs):  # ms: média, p95, máximo
    s = sorted(xs)
    return sum(s) / len(s), s[max(0, math.ceil(0.95 * len(s)) - 1)], s[-1]


def criterio(media):
    if media > 50:
        return "GATILHO DO RUST (ADR-001 sec. 9)"
    if media > 5:
        return "META NAO ATINGIDA"
    return "ok"


def cronometro(fn):  # ms
    t0 = time.perf_counter()
    fn()
    return (time.perf_counter() - t0) * 1000


def m(x):  # número em pt-BR, 3 casas
    return f"{x:.3f}".replace(".", ",")


def trio(xs):
    media, p95, mx = estat(xs)
    return f"{m(media)} / {m(p95)} / {m(mx)}"


def _tx(sessao, h, c, op):
    with sessao.escrever() as esc, h.transacao(esc) as t:
        aplicar(op, t.ifc, t.lado, c)


def _desfazer(sessao, h):
    with sessao.escrever() as esc:
        h.desfazer(esc)


def _refazer(sessao, h):
    with sessao.escrever() as esc:
        h.refazer(esc)


def medir_ops(n, sessao, h, c, f):
    rng = random.Random(SEMENTE)
    paredes = [w.GlobalId for w in f.by_type("IfcWall")]
    precisa = LOTE * n + n + 1
    if len(paredes) < precisa:
        sys.exit(f"modelo tem {len(paredes)} paredes; precisa de {precisa} (aumente --tamanho-mb)")
    rng.shuffle(paredes)
    apagar, lote, livres = paredes[:n], paredes[n:n + LOTE * n], paredes[n + LOTE * n:]
    _tx(sessao, h, c, ("pset_criar", livres[0], "setup"))  # alvo do pset, fora da medição
    lista = {  # operações sorteadas com semente; as paredes apagadas não são tocadas pelas outras
        "nome": [("nome", rng.choice(livres)) for _ in range(n)],
        "propriedade (editar valor)": [("pset_editar", "setup") for _ in range(n)],
        "posicao": [("mover", rng.choice(livres)) for _ in range(n)],
        "criar parede": [("parede", f"m{k}") for k in range(n)],
        "apagar parede": [("apagar", g) for g in apagar],
        "apagar 50 em lote": [("lote", lote[k * LOTE:(k + 1) * LOTE]) for k in range(n)],
    }
    medidas = {}
    for nome in TIPOS:
        tx, du, rf = [], [], []
        for op in lista[nome]:
            tx.append(cronometro(lambda: _tx(sessao, h, c, op)))
            du.append(cronometro(lambda: _desfazer(sessao, h)))
            rf.append(cronometro(lambda: _refazer(sessao, h)))
        medidas[nome] = (tx, du, rf)
        print(f"  {nome}: {n} operações medidas", file=sys.stderr)
    return medidas


def medir_arquivos(n, ifc, sessao, h, lat, tmp, lado):
    d = Diario.abrir(lado, ifc)
    linha = [("notas", "o1", None, {"texto": "nota", "n": 1})]  # payload pequeno, ~120 bytes na linha
    diario = [cronometro(lambda: d.anotar("transacao", [], linha)) for _ in range(n)]
    au = Autosave(sessao, h, lat, d, lado, ifc)
    au.anotar("transacao", [], linha)
    t_auto = cronometro(au.salvar)
    destino = tmp / "gravacao" / "Casa.ifc"
    destino.parent.mkdir(parents=True, exist_ok=True)
    t_par = cronometro(lambda: gravar_par(sessao, h, lat, destino, pasta_projeto(lado), lado, d.ultimo_seq))
    d.fechar()
    return diario, t_auto, t_par


def medir_windows(pasta, reps=1000):  # só no Windows; no Linux devolve vazio
    if sys.platform != "win32":
        return {}
    p = Path(pasta)
    p.mkdir(parents=True, exist_ok=True)
    a, b, out = p / "a.bin", p / "b.bin", {}
    bloco = b"x" * 4096

    def gravar(caminho):
        with open(caminho, "wb") as f:
            f.write(bloco)
            f.flush()
            os.fsync(f.fileno())

    def fsync_pasta():
        fd = os.open(p, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    def troca():
        gravar(b)
        os.replace(b, a)

    contador = count()

    def link():
        nome = p / f"l{next(contador)}.bin"
        os.link(a, nome)
        os.remove(nome)

    gravar(a)
    for rotulo, fn in (("fsync do arquivo (4 KB)", lambda: gravar(a)), ("fsync da pasta", fsync_pasta),
                       ("troca por os.replace (4 KB)", troca), ("criacao de link (os.link)", link)):
        try:
            out[rotulo] = estat([cronometro(fn) for _ in range(reps)])
        except OSError as e:
            out[rotulo] = f"erro: {e}"
    return out


def bateria():
    arqs = [str(p) for pre in ("test_s05_t04", "test_s05_t05", "test_s05_t07") for p in sorted((RAIZ / "tests").glob(pre + "*.py"))]
    env = dict(os.environ, OBIM_S05_OBRIGATORIO="1")  # sem módulo, vira falha (não pula)
    t0 = time.perf_counter()
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *arqs], cwd=RAIZ, env=env,
                       capture_output=True, text=True, timeout=7200)
    seg = time.perf_counter() - t0
    fim = ([x for x in (r.stdout + r.stderr).splitlines() if re.search(r"\d+ (passed|failed|errors?|skipped|xfailed)", x)] or [""])[-1]
    cont = {k: int(g.group(1)) for k, rx in (("passed", "passed"), ("failed", "failed"), ("errors", "errors?"),
                                              ("skipped", "skipped"), ("xfailed", "xfailed"), ("xpassed", "xpassed"))
            if (g := re.search(rf"(\d+) {rx}\b", fim))}
    return len(arqs), cont, seg, r.returncode


def relatorio(a, info, medidas, diario, t_auto, t_par, win, bat, descartados):
    L = ["# Medição S05 (F0-S05-T10)", "",
         f"Modelo: {info['paredes']} paredes, {info['entidades']} entidades, {info['bytes'] / 1e6:.2f} MB, sha256 `{info['sha']}`"
         + (" (igual ao T02)" if info["sha"] == SHA_T02 else " (diferente do T02; tamanho ou gerador mudou)"),
         f"Operações por tipo: {a.n_ops}; máquina: {platform.system()} {platform.release()}, Python {sys.version.split()[0]}", "",
         "## Metas", "", "| Meta | Limite | Medido (ms) | Status |", "| --- | --- | --- | --- |"]
    pior = max(P3, key=lambda k: estat(medidas[k][0])[0])
    media_pior = estat(medidas[pior][0])[0]
    L.append(f"| Aplicar 1 operação pequena (P3: nome, propriedade, posicao), média | 5 ms | pior: {pior}, média / p95 / máx {trio(medidas[pior][0])} | {criterio(media_pior)} |")
    L.append(f"| Desfazer e refazer de uma operação (P3, pior), média | informativo | desfazer {m(estat(medidas[pior][1])[0])}; refazer {m(estat(medidas[pior][2])[0])} | ok |")
    L += ["", "## Operações (cada uma numa transação, com registro do desfazer; ms)", "",
          "| Operação | Transação média / p95 / máx | Desfazer média / p95 / máx | Refazer média / p95 / máx | Papel | Status (média) |",
          "| --- | --- | --- | --- | --- | --- |"]
    for nome in TIPOS:
        tx, du, rf = medidas[nome]
        papel = "P3 (conta para a meta)" if nome in P3 else "informativo (fora da P3)"
        status = criterio(estat(tx)[0]) if nome in P3 else "informativo (nao conta para a meta)"
        L.append(f"| {nome} | {trio(tx)} | {trio(du)} | {trio(rf)} | {papel} | {status} |")
    L += ["", "## Outras medidas", "", "| Item | Medido (ms) | Status / nota |", "| --- | --- | --- |",
          f"| Diário: anotar 1 linha pequena, média / p95 / máx ({len(diario)} vezes) | {trio(diario)} | à parte (P3), fora da meta |",
          f"| Autosave.salvar (modelo inteiro) | {m(t_auto)} | informativo |",
          f"| gravar_par (par inteiro) | {m(t_par)} | informativo |",
          f"| Passos descartados pelo limite de 256 MB do desfazer | {descartados} | ok se 0 ou esperado |"]
    if bat is None:
        L.append("| Bateria T04/T05/T07 | não rodada | fumaça (n-ops < 1000) ou --sem-bateria |")
    else:
        n_arq, cont, seg, rc = bat
        ruim = cont.get("failed", 0) + cont.get("errors", 0) > 0 or rc != 0
        resumo = ", ".join(f"{v} {k}" for k, v in cont.items()) or f"código {rc}"
        L.append(f"| Bateria T04/T05/T07 ({n_arq} arquivos): {resumo}; tempo {m(seg)} s | {m(seg * 1000)} | "
                 f"{'META NAO ATINGIDA' if ruim else 'ok'} |")
    if win:
        for rotulo, v in win.items():
            L.append(f"| Windows: {rotulo}, média / p95 / máx | {trio_v(v)} | informativo |")
    else:
        L.append("| Windows: fsync do arquivo e da pasta, os.replace, os.link | n/d | medido só no Windows (CI ou PO) |")
    return "\n".join(L)


def trio_v(v):
    return v if isinstance(v, str) else f"{m(v[0])} / {m(v[1])} / {m(v[2])}"


def executar(a, tmp):
    paredes = PAREDES_T02 if a.tamanho_mb == 50 else round(a.tamanho_mb * PAREDES_T02 / BYTES_T02_MB)
    ifc = tmp / "modelo.ifc"
    t0 = time.perf_counter()
    gerar(str(ifc), paredes=paredes)
    print(f"modelo: {paredes} paredes em {time.perf_counter() - t0:.1f} s", file=sys.stderr)
    f, c, _ = montar(str(ifc))
    info = {"paredes": paredes, "entidades": sum(1 for _ in f), "bytes": ifc.stat().st_size, "sha": sha256(ifc)}
    sessao, lat = SessaoModelo(f), Lateral()
    h = Historico(sessao, lat)  # limite de 256 MB (ADR-002 §4.6), sem diário nesta parte
    medidas = medir_ops(a.n_ops, sessao, h, c, f)
    diario, t_auto, t_par = medir_arquivos(a.n_ops, ifc, sessao, h, lat, tmp, "medicao-s05")
    win = medir_windows(tmp / "win")
    bat = None if (a.sem_bateria or a.n_ops < 1000) else bateria()
    return relatorio(a, info, medidas, diario, t_auto, t_par, win, bat, h.descartados)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n-ops", type=int, default=1000, help="operações por tipo (padrão 1000)")
    ap.add_argument("--tamanho-mb", type=float, default=50.0, help="tamanho aproximado do modelo sintético (padrão 50)")
    ap.add_argument("--saida", help="grava a tabela markdown neste caminho")
    ap.add_argument("--sem-bateria", action="store_true", help="não roda a bateria dos oráculos")
    a = ap.parse_args()
    if a.n_ops < 1 or a.tamanho_mb <= 0:
        ap.error("--n-ops e --tamanho-mb devem ser > 0")
    tmp = Path(tempfile.mkdtemp(prefix="s05_medir_"))
    os.environ["OBIM_PASTA_LOCAL"] = str(tmp / "pasta_local")  # o diário e o autosave não vão à pasta do PO
    try:
        texto = executar(a, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(texto)
    if a.saida:
        Path(a.saida).write_text(texto + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
