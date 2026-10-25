# SPDX-License-Identifier: AGPL-3.0-or-later
"""Provas do R1-j com o Python do PRÓPRIO instalador (só test_instalador_ponte.sh chama; par de packaging/linux/ponte_no_pacote.py).
Uso: `env\\python.exe -I ponte_no_pacote_win.py COMANDO RAIZ [...]`, RAIZ = pasta instalada (a que tem app\\ e env\\). Só biblioteca padrão.
  freeze RAIZ  freeze_support() em main.py e no .pyw (ast) | vcrt RAIZ  prova 7: runtime do Visual C++ >= ligador do .pyd (cabeçalho PE)
  dlls RAIZ  módulos do processo só do pacote ou do Windows | spawn RAIZ SAIDA  filho spawn (SAIDA: arquivo de texto, pythonw não tem stdout)
  pytest RAIZ TESTES SITE PASTA  R1-a/d/e/i do tests/test_s04_ponte.py sem editar | autoteste  partes sem Windows (PE fabricado, ast)
Roda por caminho de arquivo, como o atalho roda o .pyw (o filho spawn reimporta este arquivo). OBIM_TESTE_SIMULADO=1: ensaio em Linux, proibido no Windows.
"""
import ast
import ctypes
import importlib.machinery
import multiprocessing
import os
import re
import struct
import subprocess
import sys
import traceback

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "linux"))  # no fim: o pacote vence
from ponte_no_pacote import GRUPOS, Contador, freeze_em_main  # noqa: E402  (mesma regra de main.py e mesma contagem de casos do Linux)

SIM = os.environ.get("OBIM_TESTE_SIMULADO") == "1"
SAIDA = None
PYTEST_MODULOS = {"pytest", "_pytest", "pluggy", "iniconfig", "pygments", "packaging", "colorama", "py"}  # só estes vêm de fora (passo de teste)
PERMITIDOS = PYTEST_MODULOS | {"test_s04_ponte", "s04_aux", "gerar_modelo_grande", "ponte_no_pacote", "__main__", "__mp_main__"}
# Estes NUNCA podem vir do Windows: têm de ser os do pacote (um Qt, OCCT ou runtime do sistema passaria despercebido).
NUCLEO = re.compile(r"^(qt6|pyside|shiboken|tk[a-z0-9]+\.dll|.*ifcopenshell|.*ifcgeom|.*obimcore|python3|vcruntime140|msvcp140|vcomp140|concrt140|vccorlib140|boost_|libopenblas)", re.I)
EXIGIDAS = {"ifcopenshell": r"_ifcopenshell_wrapper", "Qt6Core": r"^Qt6Core\.dll", "PySide6 QtCore": r"^QtCore\.(pyd|abi3\.pyd|cp\d+)",
            "obimcore": r"^_obimcore", "TKernel": r"^TKernel\.dll", "vcruntime140": r"^vcruntime140\.dll", "python": r"^python3\d*\.dll"}
EXIGIDAS_FIM = {**EXIGIDAS, "OCCT da geometria": r"^TK(BRep|Geom|Prim|Mesh|BO)"}  # só carregam quando a geometria roda

def dizer(*partes):
    texto = " ".join(map(str, partes))
    if SAIDA:
        open(SAIDA, "a", encoding="utf-8").write(texto + "\n")
    elif sys.stdout is not None:
        print(texto)

def norm(caminho):
    c = os.path.realpath(caminho)  # expande nomes curtos (RUNNER~1) e links
    return os.path.normcase(c[4:] if c.startswith("\\\\?\\") else c)

def dentro(caminho, raiz):
    c, r = norm(caminho), norm(raiz)
    return c == r or c.startswith(r + os.sep)

def subpastas_do_lancador(raiz):
    """As pastas que OpenBIM-Studio.pyw::iniciar põe no PATH e em add_dll_directory: lidas dele, para o teste montar o ambiente igual."""
    m = re.search(r"for sub in (\([^)]*\)):", open(os.path.join(raiz, "app", "OpenBIM-Studio.pyw"), encoding="utf-8").read())
    return ast.literal_eval(m.group(1)) if m else sys.exit("ERRO: não achei 'for sub in (...)' no OpenBIM-Studio.pyw")

def preparar(raiz):  # igual ao lançador: PATH e pastas de DLL do env\, depois o caminho do app\
    env = os.path.join(raiz, "env")
    for sub in subpastas_do_lancador(raiz):
        pasta = os.path.join(env, sub)
        if os.path.isdir(pasta):
            os.environ["PATH"] = pasta + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(pasta)
    sys.path.insert(0, os.path.join(raiz, "app"))
    os.environ["PYTHONPATH"] = os.path.join(raiz, "app")  # o filho do R1-e roda sem -I e herda isto (o lançador real não faz isto: só ajuda o teste)

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

def pe_inicio(b):
    if b[:2] != b"MZ" or len(b) < 0x40:
        raise ValueError("não é um arquivo PE (sem MZ)")
    pe = struct.unpack_from("<I", b, 0x3C)[0]
    if b[pe:pe + 4] != b"PE\0\0":
        raise ValueError("sem a assinatura PE")
    return pe

def versao_ligador(b):  # (maior, menor) do ligador que gerou o arquivo: MSVC 14.NN = conjunto de ferramentas NN; só maior.menor, sem número de build
    pe = pe_inicio(b)
    return b[pe + 26], b[pe + 27]

def versao_arquivo(b):  # (a, b, c, d) do VS_FIXEDFILEINFO do recurso de versão (assinatura 0xFEEF04BD seguida de StrucVersion 0x00010000)
    i = b.find(b"\xbd\x04\xef\xfe")
    while i >= 0:
        if b[i + 4:i + 8] == b"\x00\x00\x01\x00":
            ms, ls = struct.unpack_from("<II", b, i + 8)
            return ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF
        i = b.find(b"\xbd\x04\xef\xfe", i + 1)
    raise ValueError("sem recurso de versão (VS_FIXEDFILEINFO)")

def ler(caminho):
    return open(caminho, "rb").read()

RT = re.compile(r"(vcruntime140|msvcp140|vcomp140|concrt140|vccorlib140)\w*\.dll", re.I)

def ligador_do_pyd(raiz):  # (versão do ligador, erros); só o app\obimcore\_obimcore*.pyd que o build.sh gerou
    pasta = os.path.join(raiz, "app", "obimcore")
    achados = [n for n in sorted(os.listdir(pasta)) if re.fullmatch(r"_obimcore.*\.pyd", n)]
    if len(achados) != 1:
        return None, [f"esperava 1 app\\obimcore\\_obimcore*.pyd, achei {len(achados)}"]
    try:
        lig = versao_ligador(ler(os.path.join(pasta, achados[0])))
    except ValueError as e:
        return None, [f"{achados[0]}: {e}"]
    return lig, [f"ligador {lig[0]}.{lig[1]} no .pyd: esperava 14.x; a leitura não é confiável"] * (lig[0] != 14)

def runtime_vs_ligador(caminhos, lig, rotulo):
    erros = []
    for c in caminhos:
        try:
            v = versao_arquivo(ler(c))
        except ValueError as e:
            erros.append(f"{c}: {e}")
            continue
        dizer(f"   {rotulo}: {c} {'.'.join(map(str, v))} (ligador do .pyd {lig[0]}.{lig[1]})")
        erros += [f"{c}: runtime {v[0]}.{v[1]} é MAIS VELHO que o ligador do .pyd {lig[0]}.{lig[1]} (prova 7 do ADR-005)"] * (v[:2] < lig)
    return erros

def cmd_vcrt(raiz):  # prova 7: toda cópia do runtime do Visual C++ no pacote é igual ou mais nova que o compilador do .pyd
    lig, erros = ligador_do_pyd(raiz)
    if lig is None:
        return erros
    pastas = (os.path.join(raiz, "env"), os.path.join(raiz, "env", "Library", "bin"))
    achadas = [os.path.join(p, n) for p in pastas if os.path.isdir(p) for n in sorted(os.listdir(p)) if RT.fullmatch(n)]
    erros += [f"o pacote não tem {n} em env\\ nem em env\\Library\\bin" for n in ("vcruntime140.dll", "msvcp140.dll") if not any(os.path.basename(c).lower() == n for c in achadas)]
    return erros + runtime_vs_ligador(achadas, lig, "no pacote")

def modulos_carregados():  # ([caminhos dos módulos do processo], pasta do Windows)
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    ptr, u32 = ctypes.c_void_p, ctypes.c_uint32  # handles de 64 bits: c_void_p, nunca o int padrão
    k.GetCurrentProcess.restype = ptr
    k.K32EnumProcessModules.argtypes, k.K32EnumProcessModules.restype = [ptr, ctypes.POINTER(ptr), u32, ctypes.POINTER(u32)], ctypes.c_int
    k.K32GetModuleFileNameExW.argtypes, k.K32GetModuleFileNameExW.restype = [ptr, ptr, ctypes.c_wchar_p, u32], u32
    k.GetWindowsDirectoryW.argtypes = [ctypes.c_wchar_p, u32]
    h, n = k.GetCurrentProcess(), 1024
    while True:  # uma volta para medir o vetor, outra para ler
        lista, preciso = (ptr * n)(), u32()
        if not k.K32EnumProcessModules(h, lista, ctypes.sizeof(lista), ctypes.byref(preciso)):
            raise OSError(ctypes.get_last_error(), "EnumProcessModules falhou")
        if preciso.value <= ctypes.sizeof(lista):
            break
        n = preciso.value // ctypes.sizeof(ptr) + 64
    buf, win = ctypes.create_unicode_buffer(32768), ctypes.create_unicode_buffer(1024)
    k.GetWindowsDirectoryW(win, 1024)
    return [buf.value for m in lista[:preciso.value // ctypes.sizeof(ptr)] if m and k.K32GetModuleFileNameExW(h, m, buf, 32768)], win.value

def importados(caminho):  # nomes (minúsculos) das DLLs da tabela de importação de um PE; arquivo que não é PE ou ilegível: vazio
    try:
        with open(caminho, "rb") as f:
            b = f.read(8192)
            pe = pe_inicio(b)
            nsec, tam_opt = struct.unpack_from("<H", b, pe + 6)[0], struct.unpack_from("<H", b, pe + 20)[0]
            opt = pe + 24
            rva = struct.unpack_from("<I", b, opt + (112 if struct.unpack_from("<H", b, opt)[0] == 0x20B else 96) + 8)[0]
            secoes = [struct.unpack_from("<IIII", b, opt + tam_opt + 40 * i + 8) for i in range(nsec)]  # (tamanho virtual, rva, tamanho em disco, posição)

            def pos(r):
                return next((p + r - va for v, va, t, p in secoes if va <= r < va + max(v, t)), None)
            nomes, d = set(), pos(rva) if rva else None
            while d is not None:
                f.seek(d)
                desc = f.read(20)
                nome = struct.unpack_from("<I", desc, 12)[0] if len(desc) == 20 else 0
                if not nome or pos(nome) is None:
                    break
                f.seek(pos(nome))
                nomes.add(f.read(256).split(b"\0")[0].decode("ascii", "replace").lower())
                d += 20
            return nomes
    except (OSError, ValueError, struct.error):
        return set()


def do_pacote(raiz):  # (nomes minúsculos de toda DLL/PYD do pacote, nomes que elas importam)
    arqs = [os.path.join(p, n) for p, _, ns in os.walk(raiz) for n in ns if n.lower().endswith((".dll", ".pyd"))]
    return {os.path.basename(a).lower() for a in arqs}, set().union(*(importados(a) for a in arqs))


def longo(c):  # nome longo (resolve 8.3 tipo TKERNE~1.DLL) quando o Windows está disponível
    if hasattr(ctypes, "windll"):
        buf = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.kernel32.GetLongPathNameW(c, buf, 32768):
            return buf.value
    return c


def classificar(mods, windir, raiz, devs, pastas_path, nomes, importadas, resolver=longo):
    """(erros, avisos). Módulo de fora do pacote: do Windows só se não for núcleo. Fora do pacote E do Windows (ex.: MpOav.dll, provedor AMSI do Defender,
    injetado no processo pelo antivírus do runner) REPROVA se (a) está sob o prefixo do ambiente de desenvolvimento, (b) está numa pasta do PATH herdado
    (conda base, Git...: é entrada por busca de nome), (c) tem o mesmo nome de DLL/PYD do pacote ou é importado por algum PE do pacote (dependência que veio
    de fora), (d) é núcleo, ou (e) tem nome curto 8.3 que não se resolveu. O resto vira AVISO: o propósito é nenhuma 2ª cópia de núcleo e nenhum
    vazamento do ambiente de desenvolvimento, sem lista de exceções por nome."""
    erros, avisos = [], []
    for c0 in mods:
        c = resolver(c0)
        base = os.path.basename(norm(c))
        if dentro(c, raiz):
            continue
        if dentro(c, windir):
            erros += ["do Windows, devia ser a do pacote: " + c] * bool(NUCLEO.search(base))
        elif re.search(r"~\d", base):
            erros.append(f"nome curto 8.3 que não se resolveu, não dá para classificar: {c}")
        elif any(dentro(c, p) for p in devs):
            erros.append("carregada do ambiente de DESENVOLVIMENTO (vazamento): " + c)
        elif norm(os.path.dirname(c)) in pastas_path:
            erros.append("carregada de uma pasta do PATH herdado (entrou por busca de nome, não do pacote): " + c)
        elif base.lower() in nomes or base.lower() in importadas:
            erros.append(f"carregada de fora do pacote, mas o pacote a tem ou a importa ({base}): {c}")
        elif NUCLEO.search(base):
            erros.append("núcleo carregado de FORA do pacote e do Windows: " + c)
        else:
            avisos.append(c)
    return erros, avisos


def auditar_dlls(raiz, exigir):
    mods, windir = modulos_carregados()
    devs = [p for p in os.environ.get("OBIM_DEV_PREFIXES", "").split("|") if p]
    path = {norm(p) for p in os.environ.get("PATH", "").split(os.pathsep) if p and not dentro(p, raiz) and not dentro(p, windir)}
    erros, avisos = classificar(mods, windir, raiz, devs, path, *do_pacote(raiz))
    dizer(f"   prefixos de desenvolvimento: {devs}; pastas do PATH herdado fora do pacote e do Windows: {len(path)}")
    erros += ["OBIM_DEV_PREFIXES vazio: a prova de vazamento do ambiente de desenvolvimento estaria desligada"] * (not devs)
    for c in avisos:
        dizer("AVISO: módulo de terceiros fora do pacote (não reprova):", c)
    return erros + [f"nenhum módulo '{nome}' do pacote aparece carregado (a prova não viu o que devia ver)" for nome, rx in exigir.items()
                    if not any(re.search(rx, os.path.basename(c), re.I) and dentro(c, raiz) for c in mods)]


def usar_nucleos():  # o processo USA geometria (OCCT) e o módulo C++ antes de listar: no Windows o TKernel só carrega quando a geometria roda
    import ifcopenshell.api
    import ifcopenshell.geom
    import obimcore
    api = ifcopenshell.api.run
    f = api("project.create_file", version="IFC4")
    api("root.create_entity", f, ifc_class="IfcProject")
    api("unit.assign_unit", f)
    corpo = api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=api("context.add_context", f, context_type="Model"))
    w = api("root.create_entity", f, ifc_class="IfcWall", name="W")
    api("geometry.assign_representation", f, product=w, representation=api("geometry.add_wall_representation", f, context=corpo, length=3.0, height=2.5, thickness=0.2))
    cfg = ifcopenshell.geom.settings()
    cfg.set("use-world-coords", True)
    forma = ifcopenshell.geom.create_shape(cfg, w, geometry_library="hybrid-cgal-simple-opencascade").geometry
    m = obimcore.malhas(f, [w.GlobalId])
    return [] if len(forma.verts) > 0 and len(m) == 1 else [f"a geometria mínima não deu resultado (vértices {len(forma.verts)}, malhas {len(m)})"]


def nucleos_do_modulo(raiz):  # o que o R1-e conta: obimcore.bibliotecas_carregadas() tem uma cópia de cada núcleo e ela é do pacote
    import obimcore
    lib, erros = obimcore.bibliotecas_carregadas(), []
    dizer("   obimcore.bibliotecas_carregadas():", *map(str, lib))
    for nome, rx in (("TKernel", "tkernel"), ("Qt6Core", "qt6core")):
        achadas = sorted({norm(c) for c in lib if rx in os.path.basename(c).lower()})
        erros += [f"{nome}: {len(achadas)} cópia(s) em bibliotecas_carregadas() (esperava 1): {achadas}"] * (len(achadas) != 1)
    erros += [f"bibliotecas_carregadas() lista um módulo de fora do pacote: {c}" for c in lib if not dentro(c, raiz)]
    return erros


def diagnostico(raiz):  # na falha: tudo o que o processo carregou, para não gastar outra rodada do CI
    mods, windir = modulos_carregados()
    dizer("--- módulos sob env\\ do pacote ---", *[f"\n   {c}" for c in sorted(mods) if dentro(c, raiz)])
    dizer("--- módulos de FORA do pacote ---", *[f"\n   {c}" + ("  (Windows)" if dentro(c, windir) else "  (OUTRO)") for c in sorted(mods) if not dentro(c, raiz)])


def cmd_dlls(raiz):
    preparar(raiz)
    import ifcopenshell  # noqa: F401  (ifcopenshell antes do obimcore, como o __init__ dele)
    import ifcopenshell.geom  # noqa: F401
    import PySide6.QtCore  # noqa: F401
    import obimcore  # noqa: F401
    lig, erros = ligador_do_pyd(raiz)
    try:
        erros += usar_nucleos() + nucleos_do_modulo(raiz)
    except Exception:  # noqa: BLE001 - qualquer falha ao USAR os núcleos vira diagnóstico, nunca passa calada
        erros.append("falhou ao usar a geometria/o módulo C++ dentro do pacote:\n" + traceback.format_exc())
    carregadas = [c for c in modulos_carregados()[0] if RT.fullmatch(os.path.basename(c))]  # prova 7, parte 2: vale o que o processo usa de fato
    erros += modulos_do_pacote(raiz) + auditar_dlls(raiz, EXIGIDAS_FIM) + (runtime_vs_ligador(carregadas, lig, "carregada") if lig else [])
    if erros:
        diagnostico(raiz)
    return erros

def freeze_no_pyw(texto):
    """True se `import multiprocessing` (nível do módulo) e freeze_support() vêm antes de o lançador abrir o app: antes de chamar iniciar(), ou no começo de iniciar()."""
    corpo = ast.parse(texto).body

    def achatar(lista):  # ordem de execução: o corpo de `if __name__ == "__main__"` e de `try` entram no lugar
        return [x for n in lista for x in (achatar(n.body) if isinstance(n, ast.Try) or (isinstance(n, ast.If) and "__main__" in ast.dump(n.test)) else [n])]

    def chama(n, nome):
        return any(isinstance(c, ast.Call) and getattr(c.func, "id", "") == nome for c in ast.walk(n))

    def antes(lista, abre):  # freeze_support() é uma instrução da lista e vem antes da primeira que abre o app
        i = next((i for i, n in enumerate(lista) if isinstance(n, ast.Expr) and getattr(getattr(n.value, "func", None), "attr", "") == "freeze_support"), None)
        j = next((j for j, n in enumerate(lista) if not isinstance(n, (ast.FunctionDef, ast.ClassDef)) and abre(n)), None)
        return i is not None and j is not None and i < j
    iniciar = next((n.body for n in corpo if isinstance(n, ast.FunctionDef) and n.name == "iniciar"), [])
    return any(isinstance(n, ast.Import) and "multiprocessing" in ast.dump(n) for n in corpo) and (
        antes(achatar(corpo), lambda n: chama(n, "iniciar")) or antes(iniciar, lambda n: isinstance(n, ast.ImportFrom) or chama(n, "main")))

def cmd_freeze(raiz):
    erros = []
    main, pyw = (os.path.join(raiz, "app", *p) for p in (("openbim_app", "main.py"), ("OpenBIM-Studio.pyw",)))
    if not freeze_em_main(open(main, encoding="utf-8").read()):
        erros.append(f"{main}: falta multiprocessing.freeze_support() (nível do módulo ou no começo de main(), antes de criar a aplicação)")
    if not freeze_no_pyw(open(pyw, encoding="utf-8").read()):
        erros.append(f"{pyw}: falta multiprocessing.freeze_support() antes de abrir o app (depois de `import multiprocessing`)")
    return erros

def dobro(x, fila):  # alvo do filho; o spawn reimporta este arquivo (por isso o guarda `__main__` no fim). No Windows, obimcore ANTES do ifcopenshell:
    try:  # pythonw não tem saída de erro: o erro do filho volta pela fila
        import obimcore  # o __init__ dele mostra ao carregador onde estão as DLLs do env\; um filho não herda add_dll_directory do pai
        import ifcopenshell  # noqa: F401
        fila.put({"valor": 2 * x, "isolado": sys.flags.isolated, "exe": sys.executable, "modulo": obimcore.__file__})
    except BaseException:  # noqa: BLE001
        fila.put({"erro": traceback.format_exc(), "exe": sys.executable, "isolado": sys.flags.isolated})

def cmd_spawn(raiz, saida):
    global SAIDA
    SAIDA = saida
    preparar(raiz)  # o filho herda o sys.path do pai; PYTHONPATH não conta em -I
    ctx = multiprocessing.get_context("spawn")
    fila = ctx.Queue()
    filho = ctx.Process(target=dobro, args=(21, fila))
    filho.start()
    filho.join(120)
    if filho.is_alive():
        filho.kill()
        return ["o filho spawn não terminou em 120 s (travou ou não abriu)"]
    if filho.exitcode != 0:
        return [f"o filho spawn caiu com código {filho.exitcode}"]
    r = fila.get(timeout=10)
    if "erro" in r:
        return [f"o filho spawn não importou o obimcore (exe={r['exe']}, isolado={r['isolado']}, PATH começa por {os.environ['PATH'][:300]}):\n{r['erro']}"]
    dizer(f"filho spawn: valor={r['valor']} isolado={r['isolado']} exe={r['exe']} obimcore={r['modulo']}")
    return ([f"o filho devolveu {r['valor']}, não 42"] * (r["valor"] != 42) + ["o filho não está em modo isolado (-I)"] * (r["isolado"] != 1) +
            [f"o filho não é o Python do pacote: {r['exe']}"] * (not dentro(r["exe"], raiz)) +
            [f"o filho roda {r['exe']}, o pai roda {sys.executable}"] * (norm(r["exe"]) != norm(sys.executable)) +
            [f"o filho importou o obimcore de fora do pacote: {r['modulo']}"] * (not dentro(r["modulo"], raiz)))

class PytestDeFora:  # no FIM do meta_path: só o que o pacote não tem e só os nomes de PYTEST_MODULOS, vindos da pasta `site`
    def __init__(self, site):
        self.site = site

    def find_spec(self, nome, caminho=None, alvo=None):
        if caminho is None and nome in PYTEST_MODULOS:
            return importlib.machinery.PathFinder.find_spec(nome, [self.site])

def filhos_sem_i(raiz):  # como o R1-e: o mesmo python, SEM -I, só com PATH e PYTHONPATH herdados, nas três ordens de importação
    erros = []
    for ordem in ("PySide6.QtCore,ifcopenshell,obimcore", "ifcopenshell,obimcore,PySide6.QtCore", "ifcopenshell,PySide6.QtCore,obimcore"):
        p = subprocess.run([sys.executable, "-c", "import importlib,sys\nfor n in sys.argv[1].split(','): importlib.import_module(n)\nprint('ok')", ordem],
                           capture_output=True, text=True, errors="replace", timeout=300)
        dizer(f"   filho sem -I ({ordem}): código {p.returncode} {p.stdout.strip()[-60:]}")
        erros += [f"filho sem -I ({ordem}) falhou, código {p.returncode}:\n{p.stderr[-1500:]}"] * (p.returncode != 0)
    return erros


def cmd_pytest(raiz, testes, site, pasta):
    preparar(raiz)
    os.environ.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", OBIM_S04_OBRIGATORIO="1")
    sys.path.append(testes)
    sys.meta_path.append(PytestDeFora(site))
    import pytest
    open(os.path.join(pasta, "pytest.ini"), "w").close()
    c, erros = Contador(), filhos_sem_i(raiz)  # primeiro o diagnóstico dos filhos do R1-e (rodam sem -I): o erro de DLL aparece inteiro aqui
    rc = pytest.main(["-q", "-rsfE", "--noconftest", "-p", "no:cacheprovider", "-c", os.path.join(pasta, "pytest.ini"),
                      "--rootdir", testes, "--basetemp", os.path.join(pasta, "pytest_tmp"), "-k", "test_r1a_ or test_r1d_ or test_r1e_ or test_r1i_",
                      os.path.join(testes, "test_s04_ponte.py")], plugins=[c])
    erros += [f"pytest terminou com código {rc}"] * (rc != 0)
    for prefixo, minimo in GRUPOS.items():
        casos = {n: f for n, f in c.res.items() if n.split("::")[-1].startswith(prefixo)}
        ruins = [n for n, f in casos.items() if [f.get(k) for k in ("setup", "call", "teardown")] != ["passed"] * 3]
        erros += [f"{prefixo}*: só {len(casos)} caso(s) rodaram, esperava {minimo} ou mais (não rodou)"] * (len(casos) < minimo)
        erros += [f"não passou (pulado, reprovado ou com erro): {n} {c.res[n]}" for n in ruins]
    erros += modulos_do_pacote(raiz) + ([] if SIM else auditar_dlls(raiz, EXIGIDAS_FIM))  # de novo no fim: agora a geometria já rodou
    if erros and not SIM:
        diagnostico(raiz)
    return erros

def pe_falso(ligador=(14, 44), versao=None):  # PE mínimo fabricado: MZ, PE\0\0, cabeçalho opcional com a versão do ligador e (opcional) um VS_FIXEDFILEINFO
    b = bytearray(b"MZ" + b"\0" * 0x3A + struct.pack("<I", 0x40) + b"PE\0\0" + b"\0" * 20 + b"\x0b\x02" + bytes(ligador) + b"\0" * 200)
    if versao:
        ms, ls = (versao[0] << 16) | versao[1], (versao[2] << 16) | versao[3]
        b += b"\xbd\x04\xef\xfe" + struct.pack("<III", 0x10000, ms, ls)
    return bytes(b)

def cmd_autoteste():
    erros, F = [], "multiprocessing.freeze_support()\n"

    def ok(cond, msg):
        erros.extend([msg] * (not cond))

    def recusa(f, *a):
        try:
            f(*a)
        except ValueError:
            return True
        return False

    def fonte(imp="import multiprocessing\n", topo="", ini="", blk="", fim=""):
        return f"{imp}import sys\n\ndef iniciar():\n{ini}    return 1\n\n{topo}if __name__ == '__main__':\n{blk}    sys.exit(iniciar())\n{fim}"
    ok(versao_ligador(pe_falso((14, 44))) == (14, 44), "ligador 14.44")
    ok(versao_arquivo(pe_falso(versao=(14, 51, 36247, 0))) == (14, 51, 36247, 0), "versão do arquivo 14.51.36247.0")
    ok(versao_arquivo(b"\xbd\x04\xef\xfe" + b"\0" * 8 + pe_falso(versao=(14, 40, 1, 0))) == (14, 40, 1, 0), "assinatura falsa antes da verdadeira")
    ok(all(recusa(versao_ligador, x) for x in (b"", b"MZ" + b"\0" * 100, b"PK" + b"\0" * 100)) and recusa(versao_arquivo, pe_falso()), "PE ou versão inválidos aceitos")
    import tempfile
    raiz, win, dev, pa, fora = (tempfile.mkdtemp() for _ in range(5))
    nomes, imp = {"zlib1.dll", "qt6core.dll"}, {"liblzma.dll"}
    cls = lambda c, **kw: classificar([c], win, raiz, [dev], {norm(pa)}, nomes, imp, **kw)[0]
    ok(not cls(f"{fora}/MpOav.dll") and classificar([f"{fora}/MpOav.dll"], win, raiz, [dev], {norm(pa)}, nomes, imp)[1], "antivírus deve só avisar")
    ok(cls(f"{pa}/inocuo.dll") and cls(f"{dev}/Library/bin/inocuo.dll") and cls(f"{fora}/ZLIB1.DLL"), "PATH, prefixo de dev e mesmo nome devem reprovar")
    ok(cls(f"{fora}/liblzma.dll") and cls(f"{fora}/TKernel.dll") and cls(f"{fora}/TKERNE~1.DLL"), "importada pelo pacote, núcleo e 8.3 sem resolver devem reprovar")
    ok(cls(f"{fora}/TKERNE~1.DLL", resolver=lambda c: f"{fora}/TKernel.dll") and not cls(f"{fora}/ALGO~1.DLL", resolver=lambda c: f"{fora}/algo.dll") and not cls(f"{win}/System32/kernel32.dll") and cls(f"{win}/Qt6Gui.dll"), "8.3 resolvido, Windows")
    ok(not cls(f"{raiz}/env/Library/bin/Qt6Core.dll") and cls(f"{fora}/VCOMP140.DLL") and cls(f"{win}/System32/concrt140.dll"), "pacote ok; vcomp/concrt fora reprovam")
    ok(importados(__file__) == set(), "arquivo que não é PE não importa nada")
    imp_pe = bytearray(0x400)
    imp_pe[0:2], imp_pe[0x3C:0x40], imp_pe[0x40:0x44] = b"MZ", struct.pack("<I", 0x40), b"PE\0\0"
    struct.pack_into("<HH", imp_pe, 0x44 + 2, 1, 0)
    struct.pack_into("<H", imp_pe, 0x44 + 16, 240)
    struct.pack_into("<H", imp_pe, 0x58, 0x20B)
    struct.pack_into("<II", imp_pe, 0x58 + 112 + 8, 0x1000, 60)
    struct.pack_into("<8sIIII", imp_pe, 0x58 + 240, b".idata", 0x200, 0x1000, 0x200, 0x200)
    struct.pack_into("<I", imp_pe, 0x200 + 12, 0x1000 + 0x80)
    struct.pack_into("<I", imp_pe, 0x200 + 32, 0x1000 + 0x90)
    imp_pe[0x280:0x290], imp_pe[0x290:0x2A0] = b"LibLZMA.dll\0", b"KERNEL32.dll\0"
    p = os.path.join(raiz, "x.dll")
    open(p, "wb").write(imp_pe)
    ok(importados(p) == {"liblzma.dll", "kernel32.dll"}, f"tabela de importação fabricada: {importados(p)}")
    bons = [fonte(blk="    " + F), fonte(topo=F), fonte(ini="    " + F + "    from x import main\n")]
    ruins = [fonte(), fonte(fim="    " + F), fonte(imp="", blk="    " + F), fonte(ini="    from x import main\n    " + F)]
    erros += [f"freeze_no_pyw reprovou um caso bom #{i}" for i, t in enumerate(bons) if not freeze_no_pyw(t)]
    return erros + [f"freeze_no_pyw aprovou um caso ruim #{i}" for i, t in enumerate(ruins) if freeze_no_pyw(t)]

def main(argv):
    if argv[0] != "autoteste":
        if SIM == (sys.platform == "win32"):
            raise SystemExit("ERRO: " + ("o modo simulado é proibido no Windows" if SIM else "este teste só vale no Windows (em Linux, só OBIM_TESTE_SIMULADO=1, como ensaio)"))
        if not sys.flags.isolated:
            raise SystemExit("ERRO: rode com o Python do pacote em modo isolado (-I), como o atalho")
    if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # -I ignora PYTHONUTF8
    comandos = {"freeze": cmd_freeze, "vcrt": cmd_vcrt, "dlls": cmd_dlls, "spawn": cmd_spawn, "pytest": cmd_pytest, "autoteste": cmd_autoteste}
    erros = comandos[argv[0]](*([os.path.realpath(argv[1])] + argv[2:] if len(argv) > 1 else []))
    for e in erros:
        dizer("ERRO:", e)
    dizer("ok" if not erros else f"{len(erros)} erro(s)")
    return 1 if erros else 0

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main(sys.argv[1:]))
