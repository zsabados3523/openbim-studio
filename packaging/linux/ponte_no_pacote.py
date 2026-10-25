# SPDX-License-Identifier: AGPL-3.0-or-later
"""Provas do pacote que rodam com o Python do PRÓPRIO pacote (chamado só por test_appimage_ponte.sh).

Uso (sempre pelo `env/bin/python` do pacote, em modo -I, montado como o AppRun monta):
  freeze RAIZ                         `multiprocessing.freeze_support()` em main.py e no AppRun (leitura da árvore sintática)
  maps RAIZ                           depois de importar ifcopenshell, PySide6.QtCore e obimcore, nenhuma .so mapeada fora do pacote
  spawn RAIZ                          um processo filho `spawn` abre dentro do pacote, roda uma função e devolve o valor
  pytest RAIZ TESTES SITE_PYTEST DIR  R1-a, R1-d, R1-e e R1-i do tests/test_s04_ponte.py, sem editar o arquivo
RAIZ = pasta do pacote extraído (squashfs-root). Só biblioteca padrão no topo do arquivo: o filho `spawn` reimporta este módulo.
"""
import ast
import multiprocessing
import os
import re
import sys

SISTEMA = ("/lib/", "/lib64/", "/usr/lib/", "/usr/lib64/")  # bibliotecas do sistema (glibc etc.)
# Estas NUNCA podem vir do sistema: têm de ser as do pacote (um Qt ou OCCT do sistema passaria despercebido).
NUCLEO = re.compile(r"Qt6|PySide6|shiboken|libTK|ifcopenshell|obimcore|libpython|libboost|libstdc\+\+|libgcc_s", re.I)
EXIGIDAS = {"ifcopenshell": r"ifcopenshell", "Qt6Core": r"libQt6Core", "PySide6 QtCore": r"QtCore\.(cpython|abi3)", "obimcore": r"_obimcore",
            "TKernel": r"libTKernel"}
EXIGIDAS_FIM = {**EXIGIDAS, "OCCT da geometria": r"libTK(BRep|Geom|Prim|Mesh|BO)"}  # só mapeiam quando a geometria roda
# Fora do pacote só podem estar o pytest (injetado só neste passo de teste), os módulos do teste e este arquivo.
PERMITIDOS = {"pytest", "_pytest", "pluggy", "iniconfig", "pygments", "py", "test_s04_ponte", "s04_aux", "gerar_modelo_grande",
              "ponte_no_pacote", "__main__", "__mp_main__"}


def dentro(caminho, raiz):
    c = os.path.realpath(caminho)
    return c == raiz or c.startswith(raiz + os.sep)


def auditar_maps(raiz, exigir=()):
    """Toda .so mapeada no processo: dentro do pacote ou biblioteca do sistema que não seja do núcleo."""
    erros, vistas = [], set()
    for linha in open("/proc/self/maps", encoding="utf-8"):
        partes = linha.split(None, 5)
        if len(partes) < 6:
            continue
        caminho = partes[5].strip().removesuffix(" (deleted)")
        base = os.path.basename(caminho)
        if not re.search(r"\.so(\.|$)", base) or caminho in vistas:
            continue
        vistas.add(caminho)
        real = os.path.realpath(caminho)
        if dentro(real, raiz) or (real.startswith(SISTEMA) and not NUCLEO.search(base)):
            continue
        erros.append(f"biblioteca carregada de fora do pacote: {caminho}")
    for nome, rx in EXIGIDAS.items():
        if nome in exigir and not any(re.search(rx, c) and dentro(c, raiz) for c in vistas):
            erros.append(f"nenhuma biblioteca '{nome}' do pacote aparece mapeada (a prova não viu o que devia ver)")
    return erros


def modulos_do_pacote(raiz):
    erros = []
    for nome in ("obimcore", "ifcopenshell", "PySide6"):
        arq = getattr(sys.modules.get(nome), "__file__", None)
        if not arq or not dentro(arq, raiz):
            erros.append(f"o módulo {nome} não veio do pacote: {arq}")
    for nome, mod in sorted(sys.modules.items()):
        arq = getattr(mod, "__file__", None)
        if arq and os.path.isabs(arq) and not dentro(arq, raiz) and nome.split(".")[0] not in PERMITIDOS:
            erros.append(f"módulo '{nome}' emprestado de fora do pacote: {arq}")
    return erros


def chamada_freeze(no):
    return (isinstance(no, ast.Expr) and isinstance(no.value, ast.Call) and
            getattr(no.value.func, "attr", getattr(no.value.func, "id", "")) == "freeze_support")


def freeze_em_main(texto):
    """True se freeze_support() roda ao importar main.py (nível do módulo, FORA do `if __name__`) ou logo no começo de
    main(), antes de criar a aplicação. Importa assim porque o AppRun roda openbim_app.__main__, que importa main.py."""
    arvore = ast.parse(texto)
    if not any(isinstance(n, (ast.Import, ast.ImportFrom)) and "multiprocessing" in ast.dump(n) for n in ast.walk(arvore)):
        return False
    if any(chamada_freeze(n) for n in arvore.body):
        return True
    for fn in arvore.body:
        if isinstance(fn, ast.FunctionDef) and fn.name == "main":
            for n in fn.body:
                if chamada_freeze(n):
                    return True
                if any(isinstance(c, ast.Call) and getattr(c.func, "id", "") in ("criar_aplicacao", "QApplication") for c in ast.walk(n)):
                    return False  # criou a aplicação antes
    return False


def freeze_no_apprun(texto):
    m = re.search(r"exec .*?-c '(.*?)'", texto, re.S)  # o comando Python que o AppRun monta
    if not m:
        return False
    corpo = ast.parse(m.group(1)).body
    achou = [i for i, n in enumerate(corpo) if chamada_freeze(n)]
    corre = [i for i, n in enumerate(corpo) if "run_module" in ast.dump(n)]
    return bool(achou and corre and achou[0] < corre[0]) and "multiprocessing" in ast.dump(ast.Module(corpo, []))


def cmd_freeze(raiz):
    erros = []
    main = os.path.join(raiz, "app", "openbim_app", "main.py")
    if not freeze_em_main(open(main, encoding="utf-8").read()):
        erros.append(f"{main}: falta multiprocessing.freeze_support() (nível do módulo ou no começo de main(), antes de criar a aplicação)")
    if not freeze_no_apprun(open(os.path.join(raiz, "AppRun"), encoding="utf-8").read()):
        erros.append("AppRun: o comando Python não chama multiprocessing.freeze_support() antes de runpy.run_module")
    return erros


def cmd_maps(raiz):
    sys.path.insert(0, os.path.join(raiz, "app"))
    import ifcopenshell  # noqa: F401  (ifcopenshell antes do obimcore)
    import ifcopenshell.geom  # noqa: F401
    import PySide6.QtCore  # noqa: F401
    import obimcore  # noqa: F401
    return modulos_do_pacote(raiz) + auditar_maps(raiz, EXIGIDAS)


def dobro(x, fila):  # alvo do filho: importavel pelo filho (spawn reimporta este modulo; por isso o guarda `__main__` no fim)
    import ifcopenshell  # noqa: F401
    import obimcore
    fila.put({"valor": 2 * x, "isolado": sys.flags.isolated, "exe": sys.executable, "modulo": obimcore.__file__})


def cmd_spawn(raiz):
    sys.path.insert(0, os.path.join(raiz, "app"))  # o filho herda o sys.path do pai; PYTHONPATH não conta em -I
    ctx = multiprocessing.get_context("spawn")
    fila = ctx.Queue()
    filho = ctx.Process(target=dobro, args=(21, fila))
    filho.start()
    filho.join(90)
    if filho.is_alive():
        filho.kill()
        return ["o filho spawn não terminou em 90 s (travou ou não abriu)"]
    if filho.exitcode != 0:
        return [f"o filho spawn caiu com código {filho.exitcode}"]
    r = fila.get(timeout=10)
    erros = [f"o filho devolveu {r['valor']}, não 42"] * (r["valor"] != 42)
    erros += ["o filho não está em modo isolado (-I)"] * (r["isolado"] != 1)
    erros += [f"o filho não é o Python do pacote: {r['exe']}"] * (not dentro(r["exe"], raiz))
    erros += [f"o filho importou o obimcore de fora do pacote: {r['modulo']}"] * (not dentro(r["modulo"], raiz))
    print(f"filho spawn: valor={r['valor']} isolado={r['isolado']} exe={r['exe']} obimcore={r['modulo']}")
    return erros


class Contador:  # anota o resultado de cada caso: passou só se setup, call e teardown passaram
    def __init__(self):
        self.res = {}

    def pytest_runtest_logreport(self, report):
        self.res.setdefault(report.nodeid, {})[report.when] = report.outcome


GRUPOS = {"test_r1a_": 1, "test_r1d_mesmo_modelo": 3, "test_r1d_nome": 1, "test_r1e_": 3, "test_r1i_": 1}  # prefixo: mínimo de casos


def cmd_pytest(raiz, testes, site, pasta):
    sys.path[:0] = [os.path.join(raiz, "app"), testes]
    sys.path.append(site)  # no FIM: só enxerga o que o pacote não tem (e na pasta há só os links do pytest)
    import pytest
    c = Contador()
    rc = pytest.main(["-q", "-rsfE", "--noconftest", "-p", "no:cacheprovider", "-c", os.path.join(pasta, "pytest.ini"),
                      "--rootdir", testes, "--basetemp", os.path.join(pasta, "pytest_tmp"), "-k", "test_r1a_ or test_r1d_ or test_r1e_ or test_r1i_",
                      os.path.join(testes, "test_s04_ponte.py")], plugins=[c])
    erros = [f"pytest terminou com código {rc}"] * (rc != 0)
    for prefixo, minimo in GRUPOS.items():
        casos = {n: f for n, f in c.res.items() if n.split("::")[-1].startswith(prefixo)}
        ruins = [n for n, f in casos.items() if [f.get(k) for k in ("setup", "call", "teardown")] != ["passed"] * 3]
        erros += [f"{prefixo}*: só {len(casos)} caso(s) rodaram, esperava {minimo} ou mais (não rodou)"] * (len(casos) < minimo)
        erros += [f"não passou (pulado, reprovado ou com erro): {n} {c.res[n]}" for n in ruins]
    return erros + modulos_do_pacote(raiz) + auditar_maps(raiz, EXIGIDAS_FIM)  # de novo no fim: agora a geometria ja rodou


def main(argv):
    raiz = os.path.realpath(argv[1])
    cmd = {"freeze": cmd_freeze, "maps": cmd_maps, "spawn": cmd_spawn, "pytest": cmd_pytest}[argv[0]]
    erros = cmd(raiz, *argv[2:])
    for e in erros:
        print("ERRO:", e)
    print("ok" if not erros else f"{len(erros)} erro(s)")
    return 1 if erros else 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main(sys.argv[1:]))
