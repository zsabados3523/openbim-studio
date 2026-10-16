# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo do fluxo B, parte 2: executável com janela Qt Widgets (S04-T14; LOTE_OPUS_9 §1.1, §1.2, §2.1 a §2.3; LOTE_OPUS_22 itens 1 a 4 e 9;
contrato em prototypes/s04/fluxo_b/CONTRATO.md, "Parte 2"; apoio em tests/s04_fluxo_b_janela_aux.py, s04_fluxo_aux.py e s04_fluxo_b_aux.py).
GUARDA: pula enquanto o executável `fluxo_b_janela` não existir (OBIM_S04_FLUXO_B_EXE, OBIM_S04_FLUXO_B_DIR, PYTHONPATH ou out/s04); FALHA com OBIM_S04_T14_OBRIGATORIO=1.
Os casos que usam `prototypes/s04/medir_s04.py` pulam com "aguarda S04-T12" (falham com OBRIGATORIO): faltar a T12 nunca se confunde com faltar o executável.
Tudo gráfico roda sob `xvfb-run` (Windows: só no CI ou com OBIM_S04_TELA_VIRTUAL=1), nunca na tela real; o fluxo A de referência (roteiro R inteiro) vem do mesmo `caso("roteiro", BASE)` das T11/T12
(mesma chave de cache; OBIM_S04_SAIDA_A aponta para uma pasta de A já medida). A pasta de B fica em OBIM_S04_SAIDA_B (o `test_b_real_...` do oráculo da T12 passa a rodar na mesma sessão).
Mapa dos itens do lote 22: 1 = test_localidade_por_thread_*, 2 = test_ler_*, 3 = test_sem_python_* e test_fonte_*, 4 = test_corrida_* e test_fonte_*; 9 = test_memoria_*; "lote em thread C++" = test_b_lote_*.
Suposições do oráculo (o Opus confere): parede = 12 triângulos; a janela "não trava" = nenhum intervalo do pulso de 10 ms da thread da janela >= 100 ms (CI virtual) ou 200 ms (OBIM_S04_ESTRITO=1)."""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import s04_fluxo_aux as aux
import s04_fluxo_b_aux as bx
import s04_fluxo_b_janela_aux as jx
from test_s04_viewport import caso as _caso

caso = lambda nome, *a, **k: _caso(nome, *a, alvo=aux.AQUI, **k)  # noqa: E731  (a mesma chave do oráculo da T11)
OBRIG = os.environ.get("OBIM_S04_T14_OBRIGATORIO") == "1"
BASE = os.environ.get("OBIM_S04_BASE", "300")
FB = jx.RAIZ / "prototypes" / "s04" / "fluxo_b"
MEDIR = Path(os.environ.get("OBIM_S04_MEDIR") or jx.RAIZ / "prototypes" / "s04" / "medir_s04.py")
ROT = jx.roteiro_json()

def pular(msg):
    (pytest.fail if OBRIG else pytest.skip)(f"\n!!! S04-T14: {msg} (oráculo do fluxo B, parte 2, NÃO FOI EXECUTADO) !!!\n")

def tela():  # nunca na tela real
    if (not (os.environ.get("CI") or os.environ.get("OBIM_S04_TELA_VIRTUAL") == "1")) if sys.platform == "win32" else not shutil.which("xvfb-run"):
        pular("sem tela virtual (xvfb-run; no Windows só no CI ou com OBIM_S04_TELA_VIRTUAL=1)")

@pytest.fixture(scope="module")
def exe():
    p = jx.achar_exe()
    p or pular(f"executável {jx.NOME} ausente (build.sh de prototypes/s04/fluxo_b/; OBIM_S04_FLUXO_B_EXE, OBIM_S04_FLUXO_B_DIR, PYTHONPATH ou out/s04)")
    return p

@pytest.fixture(scope="module")
def medir(tmp_path_factory):
    if not MEDIR.is_file():
        pular(f"aguarda S04-T12: {MEDIR} ausente")
    p = subprocess.run([sys.executable, str(MEDIR), "--linhas", "--raiz", str(jx.RAIZ / "prototypes" / "s04"), "--json", str(tmp_path_factory.mktemp("m") / "l.json")], capture_output=True, text=True)
    "NotImplementedError" in p.stderr and pular("aguarda S04-T12: medir_s04.py ainda é o esqueleto")
    return MEDIR

def rodar_medir(*args):
    return subprocess.run([sys.executable, str(MEDIR), *map(str, args), *(["--estrito"] if aux.ESTRITO else [])], capture_output=True, text=True, timeout=600)

# ---------- sentinelas: rodam sem o executável ----------
def test_contrato_parte_2_descreve_o_executavel_e_os_autotestes():
    t = (FB / "CONTRATO.md").read_text(encoding="utf-8")
    assert 20 < len(t.splitlines()) <= 80 and all(x in t for x in ("fluxo_b_janela", "OBIM_S04_T14_OBRIGATORIO", "Ifc4::get_schema", "--autoteste", "pulso_janela_ms", "medicao.json", "std::mutex"))

def test_roteiro_r_tem_os_passos_que_o_contrato_cita():
    assert [p["id"] for p in ROT["passos"]] == ["1", "2", "3", "3b", "3c", "4a", "4b", "4c", "5a", "5b", "5c", "6a", "6b", "7"]

def test_validacao_do_medicao_de_b_aceita_um_correto_e_acusa_cada_defeito():
    ok = jx.sintetica(ROT)
    assert jx.validar_medicao(ok, ROT, produtos=300) == [] and jx.maior_pulso_ms(next(p for p in ok["passos"] if p["id"] == "5b")["reps"][0]) == pytest.approx(10.0)
    def mut(f):
        m = jx.sintetica(ROT)
        f(m, {p["id"]: p["reps"] for p in m["passos"]})
        return jx.validar_medicao(m, ROT, produtos=300)
    defeitos = {"fluxo A": lambda m, r: m.update(fluxo="A"), "base.produtos": lambda m, r: m["base"].update(produtos=301), "M6 preenchida": lambda m, r: m["metas"].update(M6={}),
                "passo faltando": lambda m, r: m["passos"].pop(3), "repetições a menos": lambda m, r: r["3"].pop(), "t_quadro antes de t_comando": lambda m, r: r["3"][0].update(t_quadro_ms=5.0),
                "ms_total errado": lambda m, r: r["3"][0].update(ms_total=9.0), "t_painel fora de editar": lambda m, r: r["3"][0].update(t_painel_ms=1.0), "sem t_painel em editar": lambda m, r: r["4a"][0].pop("t_painel_ms"),
                "sem relogio no 5b": lambda m, r: r["5b"][0].pop("relogio"), "mesma thread": lambda m, r: r["5b"][0].update(thread={"comando": "1", "janela": "1"}), "sem pulso": lambda m, r: r["5b"][0].pop("pulso_janela_ms"),
                "pulso fora do passo": lambda m, r: r["5b"][0].update(pulso_janela_ms=[0.0] + r["5b"][0]["pulso_janela_ms"]), "guid curto": lambda m, r: r["3"][0].update(guids=["abc"])}
    for nome, f in defeitos.items():
        assert mut(f), f"o oráculo não acusou o defeito: {nome}"

def test_fonte_cpp_da_biblioteca_tem_localidade_por_thread_esquema_explicito_mutex_e_ler_completo():  # itens 1, 3, 4 e 2 do lote 22 (o comportamento é conferido pelo executável; isto pega o atalho)
    (FB / "main.cpp").is_file() or pular("aguarda S04-T14: prototypes/s04/fluxo_b/main.cpp ainda não existe")
    todos = {p.name: re.sub(r"//[^\n]*|/\*.*?\*/", "", p.read_text(encoding="utf-8"), flags=re.S) for p in FB.iterdir() if p.suffix in (".cpp", ".h")}  # sem comentários
    lib = todos["paredes.cpp"] + todos["paredes.h"]
    assert "Ifc4::get_schema" in "".join(todos.values()), "item 3: o esquema IFC4 tem de ser referenciado em código (Ifc4::get_schema())"
    assert not re.search(r"\bsetlocale\s*\(", lib), "item 1: a biblioteca não pode mexer na localidade do processo (setlocale); use newlocale/uselocale (POSIX) ou _configthreadlocale (Windows)"
    assert re.search(r"uselocale|_configthreadlocale|_create_locale|_wcreate_locale", lib), "item 1: localidade por thread ausente"
    assert "std::mutex" in lib, "item 4: Paredes precisa de std::mutex (escritor único)"
    m = re.search(r"\bler\s*\([^)]*\)\s*(?:const\s*)?\{(.*?)\n\}", todos["paredes.cpp"], re.S)
    assert m and "logic_error" in m.group(1) and not re.search(r"default\s*:\s*return\s*(\{\s*\}|Valor\s*\(\s*\))\s*;", m.group(1)), "item 2: `ler` sem `default: return {}` e com std::logic_error no tipo não suportado"

# ---------- autotestes do executável (sem janela) ----------
def autoteste(exe, *args, env=None, rotulo=None):
    return jx.resultado(jx.rodar(exe, args, env=env, timeout=600), rotulo or " ".join(map(str, args)))

def test_sem_python_no_processo_e_esquema_ifc4_registrado_por_codigo(exe):  # item 3
    r = autoteste(exe, "--versao", env={"PATH": os.environ["PATH"], "LC_ALL": "C"})
    assert r["registro_ifc4"] is True and r["ifcopenshell"] and r["qt"], r
    libs = r["bibliotecas"]
    assert not [x for x in libs if re.search(r"python3\d*", Path(x).name.lower())], f"o executável não pode carregar Python: {libs}"
    import s04_aux
    for k, padrao in s04_aux.NUCLEOS.items():
        assert len({x for x in libs if re.search(padrao, x, re.I)}) == 1, f"{k}: esperado 1 cópia em {libs}"

def test_ler_cobre_todo_tipo_de_atributo_no_desfazer_e_refazer(exe):  # item 2: o desfazer de INT, LOGICAL, ENUMERATION, listas... não pode apagar em silêncio
    r = autoteste(exe, "--autoteste", "ler")
    obrig = {"STRING", "DOUBLE", "INTEGER", "LOGICAL", "ENUMERATION", "ENTITY", "AGGREGATE_OF_DOUBLE", "AGGREGATE_OF_ENTITY"}
    assert obrig <= r["casos"].keys(), f"faltam casos: {sorted(obrig - r['casos'].keys())}"
    for nome, c in r["casos"].items():
        assert c["antes"] not in ("", "$", "*"), f"{nome}: o valor de antes tem de ser real (não nulo), senão o caso não prova nada: {c}"
        assert c["depois_alterar"] != c["antes"], (nome, c)
        assert c["apos_desfazer"] == c["antes"] and c["apos_refazer"] == c["depois_alterar"], f"{nome}: o desfazer/refazer não devolveu o valor ({c})"
    assert r["nao_suportado"]["lancou"] is True, "tipo não suportado tem de levantar std::logic_error, não devolver nulo"

@pytest.mark.parametrize("t,n", [(2, 12), (4, 6)], ids=["2 threads", "4 threads"])
def test_localidade_por_thread_gravacoes_simultaneas_com_virgula_no_processo(exe, tmp_path, t, n):  # item 1
    r = autoteste(exe, "--autoteste", "localidade", t, n, tmp_path, env={"LC_ALL": "C"})
    if r["localidade"] is None:
        pular("SEM localidade pt_BR nesta máquina: o caso da vírgula decimal")
    assert r["virgula_no_processo"] is True, "controle: com pt_BR o processo tem de formatar com vírgula (senão o caso não prova nada)"
    assert r["decimal_depois"] == ",", "a localidade do processo tem de voltar como estava (pt_BR), não ser forçada a C"
    assert r["sondas"]["total"] > 100 and r["sondas"]["com_virgula"] == r["sondas"]["total"], f"outra thread viu a localidade mudar durante a gravação: {r['sondas']}"
    assert len(r["arquivos"]) == t * n
    ref = bx.assinatura(r["arquivos"][0])
    ws = ref["paredes"]
    assert sorted(round(w["forma"][2][0] - w["forma"][1][0], 6) for w in ws.values()) == [4.25, 4.25, 5.5], "a parede mudada tem 5,5 m e as outras 4,25 m (vírgula decimal corrompe a medida)"
    for a in r["arquivos"][1:]:
        assert bx.igual(ref, bx.assinatura(a)) == [], a
    assert not bx.validar(r["arquivos"][-1])

def test_corrida_lote_em_thread_leituras_e_segundo_escritor(exe, tmp_path):  # item 4
    r = autoteste(exe, "--autoteste", "corrida", 6, tmp_path)
    assert len(r["iteracoes"]) == 6
    ref = bx.assinatura(tmp_path / "ref.ifc")
    assert len(ref["paredes"]) == 60
    for i, it in enumerate(r["iteracoes"]):
        assert it["thread_comando"] != it["thread_principal"] and it["ocupado"] is True and it["modelo_tocado"] is False and it["paredes"] == 60, (i, it)
        assert it["leituras"] > 0 and it["maior_leitura_ms"] < 50, f"{i}: a leitura do painel durante o lote tem de usar try_lock e voltar logo ({it})"
        assert bx.igual(ref, bx.assinatura(it["arquivo"])) == [], f"{i}: o resultado com a leitura e o 2o escritor em volta difere do lote sozinho"

def test_memoria_de_10000_edicoes_cresce_menos_de_10_kb_por_edicao(exe):  # item 9 (o oráculo da T13 não media vazamento)
    r = autoteste(exe, "--autoteste", "memoria", 10000)
    cresc = (r["rss_kb_fim"] - r["rss_kb_inicio"]) / 10000
    assert cresc < 10, f"{cresc:.1f} KB por edição (RSS {r['rss_kb_inicio']} -> {r['rss_kb_fim']} KB)"

def test_entradas_invalidas_dao_codigo_2_ou_1_sem_medicao_parcial(exe, tmp_path):
    import ifcopenshell
    tela()
    ifcopenshell.file(schema="IFC2X3").write(str(tmp_path / "x23.ifc"))
    (tmp_path / "ruim.json").write_text(json.dumps({"versao": 1, "passos": [{"id": "1", "cmd": "nao_existe"}]}), encoding="utf-8")
    # sob xvfb-run (Linux) o stderr do executável vem JUNTO do stdout (o script roda o comando com `2>&1`): a mensagem é lida do fluxo unido
    casos = [("base ausente", ["--base", tmp_path / "nao_existe.ifc", "--roteiro", jx.ROTEIRO], 2, "base inválida"), ("base IFC2X3", ["--base", tmp_path / "x23.ifc", "--roteiro", jx.ROTEIRO], 2, "IFC4"),
             ("roteiro ausente", ["--roteiro", tmp_path / "nao_existe.json"], 2, "roteiro ausente"), ("comando desconhecido", ["--roteiro", tmp_path / "ruim.json"], 1, "comando desconhecido")]
    for nome, args, rc, trecho in casos:
        p = jx.rodar(exe, [*args, "--saida", tmp_path / "s"], grafico=True, env={"LC_ALL": "C"}, timeout=120)
        msg = p.stdout + p.stderr
        assert p.returncode == rc and trecho in msg and not (tmp_path / "s" / "medicao.json").exists(), (nome, p.returncode, msg[-400:])

# ---------- o roteiro R inteiro no executável, contra o fluxo A ----------
@pytest.fixture(scope="module")
def saida_a(exe):
    if os.environ.get("OBIM_S04_SAIDA_A"):
        return Path(os.environ["OBIM_S04_SAIDA_A"])
    import importlib.util
    if not (aux.PASTA / "fluxo_a.py").is_file() or importlib.util.find_spec("obimcore") is None:
        pular("fluxo A ou obimcore ausente (a referência A real)")
    tela()
    return Path(caso("roteiro", BASE, limite=900)["arquivo_medicao"]).parent

@pytest.fixture(scope="module")
def a_med(saida_a):
    return json.loads((saida_a / "medicao.json").read_text())

@pytest.fixture(scope="module")
def b(exe, saida_a, a_med, tmp_path_factory):  # o MESMO modelo de base e o MESMO roteiro, no executável de B
    tela()
    base = Path(a_med["base"]["arquivo"])
    if not base.is_file():  # A foi medido noutra máquina: o gerador produz sempre o mesmo arquivo
        import gerar_modelo_grande
        base = tmp_path_factory.mktemp("base") / "base.ifc"
        gerar_modelo_grande.gerar(str(base), paredes=int(BASE))
    pasta = tmp_path_factory.mktemp("b")
    p = jx.rodar(exe, ["--base", base, "--roteiro", jx.ROTEIRO, "--saida", pasta, "--painel-log", pasta / "painel.jsonl"], grafico=True, env={"LC_ALL": "C", "OBIM_LIMITE": "900"})
    assert p.returncode == 0 and (pasta / "medicao.json").is_file(), f"B CAIU ou falhou no roteiro (código {p.returncode}):\n{(p.stdout + p.stderr)[-3000:]}"
    assert any(x.startswith("MEDICAO ") for x in p.stdout.splitlines()[-3:]), "faltou a linha MEDICAO no fim da saída"
    os.environ["OBIM_S04_SAIDA_B"] = str(pasta)  # o test_b_real_... do oráculo da T12 lê daqui (arquivo de teste anterior, mesma sessão)
    med = json.loads((pasta / "medicao.json").read_text())
    ifc = Path(med["arquivo_ifc"]) if Path(med["arquivo_ifc"]).is_absolute() else pasta / med["arquivo_ifc"]
    return {"pasta": pasta, "med": med, "ifc": ifc, "base": base, "painel": pasta / "painel.jsonl"}

def reps(med):
    return [(p["id"], p["cmd"], x) for p in med["passos"] for x in p["reps"]]

def test_b_medicao_json_e_valido_e_mede_o_mesmo_modelo(b, a_med):
    import ifcopenshell
    g = ifcopenshell.open(str(b["base"]))
    produtos = sum(1 for p in g.by_type("IfcProduct") if p.Representation)  # conta independente do oráculo
    assert jx.validar_medicao(b["med"], ROT, produtos=produtos) == [] and produtos == a_med["base"]["produtos"]
    assert json.loads((b["pasta"] / "medicao.json").read_text())["base"]["produtos"] == produtos

def test_b_listas_sequencias_e_triangulos_iguais_aos_de_a_em_toda_repeticao(b, a_med):
    ra, rb = reps(a_med), reps(b["med"])
    assert len(ra) == len(rb)
    for (i, cmd, x), (j, cmd2, y) in zip(ra, rb):
        assert (i, cmd) == (j, cmd2)
        for k in ("guids", "criados", "alterados", "apagados", "geometria"):
            assert len(x[k]) == len(y[k]), f"{i} {cmd} #{x['r']}: {k} tem {len(y[k])} em B e {len(x[k])} em A"
        assert (x["sequencia"] is None) == (y["sequencia"] is None) and x["triangulos_cena"] == y["triangulos_cena"], f"{i} {cmd} #{x['r']}: sequência ou triângulos da cena diferem de A"
        assert "relogio" in x and "relogio" in y or "relogio" not in x and "relogio" not in y, (i, cmd)

def test_b_a_cena_tem_os_triangulos_do_ifc(b):
    por, nb = {p["id"]: p["reps"] for p in b["med"]["passos"]}, b["med"]["base"]["produtos"]
    esperado = {"1": nb, "3": nb + 200, "4a": nb + 200, "4b": nb + 200, "5b": nb + 1200, "6a": nb + 200, "6b": nb + 1200}
    assert {i: por[i][-1]["triangulos_cena"] for i in esperado} == {i: 12 * n for i, n in esperado.items()}

def test_b_metas_na_regua_do_ci_virtual_e_metas_gravadas_conferem(b):
    med, c = b["med"], aux.calcular(b["med"])
    assert not (e := aux.veredito(c)), e
    for k in ("M2", "M2b", "M3", "M4"):
        assert {a: med["metas"][k][a] for a in ("mediana_ms", "p95_ms", "max_ms")} == pytest.approx({a: c[k][a] for a in ("mediana_ms", "p95_ms", "max_ms")}, abs=1e-6), k
    print("METAS_B", json.dumps(c))

def test_b_lote_em_thread_cpp_nao_trava_a_janela(b):  # M3/M5 do cartão: durante o lote a thread da janela segue viva (pulso de 10 ms) e a viewport desenha
    x = next(p for p in b["med"]["passos"] if p["id"] == "5b")["reps"][0]
    assert x["thread"]["comando"] != x["thread"]["janela"]
    assert jx.maior_pulso_ms(x) < (200 if aux.ESTRITO else 100), f"a janela ficou {jx.maior_pulso_ms(x):.0f} ms sem tratar eventos durante o lote"
    assert aux.m5(b["med"])["maior_intervalo_ms"] < (200 if aux.ESTRITO else 100)

def test_b_painel_mostra_o_texto_novo_antes_de_t_painel_ms(b):  # M3: B não ganha pulando a pintura do painel
    log = [json.loads(x) for x in b["painel"].read_text(encoding="utf-8").splitlines() if x.strip()]
    eds = [x for i, cmd, x in reps(b["med"]) if cmd == "editar_propriedades"]
    assert len(eds) == 200 and log
    for k, x in enumerate(eds):
        novos = [e["t_ms"] for e in log if any(l.endswith(f"Parede R-{k}") for l in e["texto"].splitlines()) and x["guids"][0] in e["texto"] and "R60" in e["texto"] and "IfcWall" in e["texto"]]
        assert novos and x["t0_ms"] <= novos[0] <= x["t_painel_ms"], f"Parede R-{k}: rótulo pintado em {novos[:1]}, t_painel_ms {x['t_painel_ms']}"

def test_b_ifc_final_contem_a_base_valida_e_as_paredes_do_roteiro(b):
    import ifcopenshell
    f, g = ifcopenshell.open(str(b["ifc"])), ifcopenshell.open(str(b["base"]))
    assert f.schema == "IFC4" and "FILE_SCHEMA(('IFC4'))" in b["ifc"].read_text(encoding="latin-1")[:2000].replace(" ", "")
    nb = len(g.by_type("IfcWall"))
    assert len(f.by_type("IfcWall")) == nb + 1200 and len(f.by_type("IfcWallType")) == 1
    assert {p.GlobalId for p in g.by_type("IfcProduct") if p.Representation} <= {p.GlobalId for p in f.by_type("IfcProduct")}, "o IFC de B perdeu produtos da base"
    por = {p["id"]: p["reps"] for p in b["med"]["passos"]}
    g3, glote = [x["guids"][0] for x in por["3"]], por["5b"][0]["guids"]
    dims = lambda gs: sorted({tuple(aux.forma(f.by_guid(x))[1]) for x in gs})  # noqa: E731
    assert [f.by_guid(x).Name for x in g3] == [f"Parede R-{k}" for k in range(200)] and {aux.fire(f.by_guid(x)) for x in g3} == {"R60"}
    assert dims(g3) == [(5.0, 0.15, 2.8)] and dims(glote[::50]) == [(4.0, 0.15, 2.8)]
    assert not bx.validar(b["ifc"]), "o IFC de B tem erro de esquema ou de regra EXPRESS"

def test_b_saida_igual_a_de_a(b, a_med):  # §2.2: mesmas classes, e por parede tipo, pavimento, camadas, nome, FireRating, triângulos, caixa e volume a 1e-6
    ia = Path(a_med["arquivo_ifc"])
    assert bx.igual(jx.assin(ia), jx.assin(b["ifc"])) == [] and not bx.validar(ia)

def test_b_aceito_pelo_medir_s04(b, saida_a, medir, tmp_path):  # a ferramenta da T12 lê o mesmo medicao.json de A e de B e compara os IFCs do passo 7
    p = rodar_medir("--a", saida_a, "--b", b["pasta"], "--json", tmp_path / "ab.json")
    js = json.loads((tmp_path / "ab.json").read_text())
    assert p.returncode == 0 and js["aprovado"] and js["saida_igual"] == {"ok": True, "diferencas": []}, (js["erros"], js["saida_igual"], (p.stdout + p.stderr)[-800:])
    print("M6", json.dumps(js["m6"]))
