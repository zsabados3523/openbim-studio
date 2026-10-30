# SPDX-License-Identifier: AGPL-3.0-or-later
"""Utilitários do teste de gravação do par com diário. Código de teste; não editar.
O contrato está em `tests/test_s05_t07_par_oraculo.py`. Aqui: leitura do par (manifesto e objetos do ZIP, pset `OBIM_Projeto`), régua do par
(`estado_par`: "antigo" por bytes exatos, "novo" por conteúdo, "nada"; qualquer outra coisa é problema), escritor de par falso (só para a régua),
a mudança fixa que o caso faz no modelo (`mudar`) e o processo filho que grava (ou resolve) e morre no ponto pedido (`rodar`)."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
import zipfile
from collections import namedtuple
from pathlib import Path

import s05_conteudo_aux as R

AQUI = Path(__file__).resolve().parent
LADO = str(uuid.uuid5(uuid.UUID("2b1f6a40-7d0e-4c52-9a43-1c0de5a7f007"), "t07"))  # LadoId dado pelo chamador nos casos
SEQ = 17
SEMENTE = 20261023
TEMPS = ("Casa.ifc.tmp", "Casa.obim.tmp", "Casa.ifc.bak.tmp", "Casa.obim.bak.tmp")
CAMPOS = {"formato", "versao_formato", "LadoId", "Revisao", "ifc_nome", "ifc_sha256", "ifc_tamanho", "ifc_projeto_globalid",
          "programa_versao", "data"}  # formato do par (ADR-002 §4.3)
Antigo = namedtuple("Antigo", "ifc obim")  # bytes exatos do par de antes
Novo = namedtuple("Novo", "revisao lado_id foto lado")  # o que o par novo tem de conter (foto sem o pset OBIM_Projeto; lado = json canônico)
sha = lambda b: hashlib.sha256(b).hexdigest()  # noqa: E731


def gp():
    import openbim_app.gravacao_par as m  # primeira linha de cada caso @AINDA_NAO: hoje é ela que dá o xfail
    return m


def canon(objetos):
    from openbim_app.lateral import json_canonico
    return bytes(json_canonico(objetos))


def ler_obim(caminho):
    """(manifesto, objetos {coleção: {id: obj}}); levanta AssertionError se o ZIP tem entrada fora de `manifest.json` e `<coleção>/<id>.json`."""
    objs = {}
    with zipfile.ZipFile(caminho) as z:
        nomes = z.namelist()
        assert "manifest.json" in nomes, f"{caminho}: sem manifest.json ({nomes[:10]})"
        man = json.loads(z.read("manifest.json").decode("utf-8"))
        for n in nomes:
            if n == "manifest.json":
                continue
            partes = n.split("/")
            assert len(partes) == 2 and partes[1].endswith(".json") and len(partes[1]) > 5, f"{caminho}: entrada inesperada {n!r}"
            objs.setdefault(partes[0], {})[partes[1][:-5]] = json.loads(z.read(n).decode("utf-8"))
    return man, objs


def pset_obim(arquivo):
    import ifcopenshell.util.element as U
    projs = arquivo.by_type("IfcProject")
    assert len(projs) == 1, f"{len(projs)} IfcProject"
    n = sum(1 for r in projs[0].IsDefinedBy or () if r.is_a("IfcRelDefinesByProperties") and r.RelatingPropertyDefinition.Name == "OBIM_Projeto")
    assert n <= 1, f"{n} psets OBIM_Projeto no IfcProject (G4: um só)"
    p = U.get_pset(projs[0], "OBIM_Projeto")
    return None if p is None else (p.get("LadoId"), p.get("Revisao"))


def mudar(ifc, criar, tag):
    """A mudança fixa do caso: renomeia a primeira parede e cria um objeto no lateral. `criar(c, id, obj)` = `t.lado.criar` ou um dict."""
    ifc.by_type("IfcWall")[0].Name = f"parede alterada {tag}"
    criar("notas", f"n{tag}", {"texto": f"nota {tag} com acento: ação", "ifc_guids": [ifc.by_type("IfcWall")[1].GlobalId]})


def esperado(ifc_origem, objetos, tag, revisao):
    """O `Novo` de gravar `ifc_origem` (caminho) com `objetos` depois de `mudar(..., tag)`, sem o módulo de gravação."""
    import ifcopenshell
    f, objs = ifcopenshell.open(str(ifc_origem)), json.loads(json.dumps(objetos))
    mudar(f, lambda c, i, o: objs.setdefault(c, {}).__setitem__(i, o), tag)
    return Novo(revisao, LADO, R.foto(f, sem_pset_obim=True), canon(objs))


def sobras(destino, pasta_projeto):
    pasta = Path(destino).parent
    s = [n for n in TEMPS if (pasta / n).exists()]
    return s + [f"projeto/{p.name}" for p in Path(pasta_projeto).glob("gravacao*")]


def estado_par(destino, antigo=None, novo=None, pasta_projeto=None):
    """("antigo" | "novo" | "nada", problemas). Antigo: os DOIS arquivos com os bytes de `antigo`. Novo: par coerente (sha256 e tamanho do
    manifesto = arquivo, pset = manifesto em `LadoId`/`Revisao`, GlobalId do projeto) e com o conteúdo de `novo`. Com `pasta_projeto`, sobra
    de temporário ou de `gravacao*` é problema."""
    import ifcopenshell
    d = Path(destino)
    o = d.with_suffix(".obim")
    sob = sobras(d, pasta_projeto) if pasta_projeto is not None else []
    prob = [f"sobrou {x}" for x in sob]
    if not d.exists() and not o.exists():
        return "nada", prob
    if not (d.exists() and o.exists()):
        return "?", prob + [f"par pela metade: {d.name} {'existe' if d.exists() else 'falta'}, {o.name} {'existe' if o.exists() else 'falta'}"]
    bi, bo = d.read_bytes(), o.read_bytes()
    if antigo is not None and (bi, bo) == tuple(antigo):
        return "antigo", prob
    if antigo is not None and (bi == antigo.ifc or bo == antigo.obim):
        prob.append(f"par MISTURADO: {'IFC' if bi == antigo.ifc else 'lateral'} antigo com o outro novo")
    try:
        man, objs = ler_obim(o)
    except Exception as e:  # noqa: BLE001
        return "?", prob + [f"{o.name} não abre: {e!r}"]
    try:
        f = ifcopenshell.open(str(d))
    except Exception as e:  # noqa: BLE001
        return "?", prob + [f"{d.name} não abre: {e!r}"]
    faltam = CAMPOS - set(man)
    prob += [f"manifesto sem {sorted(faltam)}"] if faltam else []
    prob += ["manifesto tem `provisorio` (0.2.0 não tem)"] if "provisorio" in man else []
    confere = {"formato": "obim-lateral", "versao_formato": "0.2.0", "ifc_nome": d.name, "ifc_sha256": sha(bi),
               "ifc_tamanho": len(bi), "ifc_projeto_globalid": f.by_type("IfcProject")[0].GlobalId}
    prob += [f"manifesto {k} = {man.get(k)!r}, esperado {v!r}" for k, v in confere.items() if man.get(k) != v]
    try:
        ps = pset_obim(f)
    except Exception as e:  # noqa: BLE001
        return "?", prob + [f"pset OBIM_Projeto ilegível: {e!r}"]
    if ps != (man.get("LadoId"), man.get("Revisao")):
        prob.append(f"pset OBIM_Projeto {ps} difere do manifesto ({man.get('LadoId')}, {man.get('Revisao')})")
    if novo is None:
        return "?", prob + ["par que não é o antigo e nenhum novo esperado"]
    if ps != (novo.lado_id, novo.revisao) or not isinstance(ps[1], int):
        prob.append(f"pset {ps}, esperado ({novo.lado_id}, {novo.revisao})")
    prob += [f"IFC: {x}" for x in R.diferencas(R.foto(f, sem_pset_obim=True), novo.foto)[:5]]
    if canon(objs) != novo.lado:
        prob.append(f"lateral do ZIP difere: {canon(objs)[:200]!r} contra {novo.lado[:200]!r}")
    return "novo", prob


def escrever_par_falso(destino, ifc_origem, objetos, revisao, lado_id=LADO, manifesto=None, legado=False):
    """Só para a régua: grava um par como o ADR-002 §4.3 descreve, sem o módulo de gravação; `manifesto` sobrescreve campos; `legado=True` = o 0.1.0 provisório da S05."""
    import ifcopenshell
    import ifcopenshell.api
    f = ifcopenshell.open(str(ifc_origem))
    proj = f.by_type("IfcProject")[0]
    ps = ifcopenshell.api.run("pset.add_pset", f, product=proj, name="OBIM_Projeto")
    ifcopenshell.api.run("pset.edit_pset", f, pset=ps, properties={"LadoId": lado_id, "Revisao": revisao})
    d = Path(destino)
    f.write(str(d))
    b = d.read_bytes()
    man = {"formato": "obim-lateral", "versao_formato": "0.1.0" if legado else "0.2.0", **({"provisorio": True} if legado else {}), "LadoId": lado_id, "Revisao": revisao, "ifc_nome": d.name,
           "ifc_sha256": sha(b), "ifc_tamanho": len(b), "ifc_projeto_globalid": proj.GlobalId, "programa_versao": "0", "data": "2026-10-24T00:00:00Z",
           **(manifesto or {})}
    with zipfile.ZipFile(d.with_suffix(".obim"), "w") as z:
        z.writestr("manifest.json", json.dumps(man))
        for c, objs in objetos.items():
            for i, obj in objs.items():
                z.writestr(f"{c}/{i}.json", json.dumps(obj))


def copiar(de, para):
    shutil.rmtree(para, ignore_errors=True)
    shutil.copytree(de, para)


def foto_pastas(*pastas):
    return {str(p): sorted((x.relative_to(p).as_posix(), x.read_bytes()) for x in Path(p).rglob("*") if x.is_file()) for p in pastas}


FILHO = r'''import json, os, sys
cfg = json.loads(sys.argv[1]); sys.path[:0] = [cfg["app"], cfg["tests"]]
from pathlib import Path
import ifcopenshell
from openbim_app import gravacao_atomica as GA, gravacao_par as GP
from openbim_app.lateral import Lateral
from openbim_app.sessao_modelo import SessaoModelo
from openbim_app.transacao import Historico
import s05_t07_aux as X
eventos, morte = [], cfg.get("morte")
def ev(*e, depois=False):
    if (not depois and morte == len(eventos)) or morte == list(e) + (["depois"] if depois else []):
        Path(cfg["traco"]).write_text(json.dumps(eventos)); os._exit(86)
    depois or eventos.append(list(e))
def hook(nome, real):
    def f(*a, **k):
        alvo = Path(a[1] if nome == "replace" else a[0]).name
        ev(nome, alvo); r = real(*a, **k); ev(nome, alvo, depois=True); return r
    return f
destino, pasta = Path(cfg["destino"]), Path(cfg["pasta"])
if cfg["modo"] == "gravar":
    f = ifcopenshell.open(str(destino if destino.exists() else cfg["base"]))
    lat = Lateral(X.ler_obim(destino.with_suffix(".obim"))[1] if destino.with_suffix(".obim").exists() else None)
    s = SessaoModelo(f); h = Historico(s, lat)
    with s.escrever() as esc, h.transacao(esc) as t:
        X.mudar(t.ifc, t.lado.criar, cfg["tag"])
etapa_real, escrever_real = GA._etapa, ifcopenshell.file.write
def etapa(nome, caminho):
    ev("etapa", nome, Path(caminho).name); return etapa_real(nome, caminho)
def escrever(self, caminho, *a, **k):
    ev("ifc_write", Path(caminho).name); r = escrever_real(self, caminho, *a, **k)
    if morte == "ifc_cortado":
        p = Path(caminho); p.write_bytes(p.read_bytes()[: p.stat().st_size // 2]); ev("ifc_cortado", p.name, depois=True); os._exit(86)
    return r
GA._etapa, ifcopenshell.file.write = etapa, escrever
os.replace, os.unlink, os.remove = hook("replace", os.replace), hook("unlink", os.unlink), hook("unlink", os.remove)
ao = lambda seq: ev("ao_concluir", seq)
print("pronto", flush=True)
if cfg["modo"] == "gravar":
    GP.gravar_par(sessao=s, historico=h, lateral=lat, destino=destino, pasta_projeto=pasta, lado_id=X.LADO, seq=X.SEQ, ao_concluir=ao)
else:
    GP.resolver_gravacao_pendente(pasta_projeto=pasta, destino=destino, ao_concluir=ao)
Path(cfg["traco"]).write_text(json.dumps(eventos))
'''


def rodar(destino, pasta_projeto, modo="gravar", morte=None, tag=2, base=None, popen=False):
    """Roda o filho: grava o par (`mudar` com `tag` e `gravar_par`) ou só resolve. `morte`: índice do evento (morre ANTES dele), lista
    [tipo, alvo] (antes), [tipo, alvo, "depois"] ou "ifc_cortado". Devolve (código de saída, eventos até ali)."""
    import openbim_app
    traco = Path(pasta_projeto).parent / f"traco-{os.getpid()}.json"
    traco.unlink(missing_ok=True)
    cfg = {"app": str(Path(openbim_app.__file__).resolve().parent.parent), "tests": str(AQUI), "destino": str(destino), "pasta": str(pasta_projeto),
           "modo": modo, "morte": morte, "tag": tag, "base": str(base), "traco": str(traco)}
    cmd = [sys.executable, "-c", FILHO, json.dumps(cfg)]
    if popen:
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True), traco
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    assert r.returncode in (0, 86), f"filho {modo} morte={morte}: código {r.returncode}\n{r.stderr[-3000:]}"
    return r.returncode, json.loads(traco.read_text()) if traco.exists() else []
