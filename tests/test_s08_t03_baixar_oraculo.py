# SPDX-License-Identifier: AGPL-3.0-or-later
"""Oráculo F0-S08-T03: download do corpus (API fixada no cartão). Só servidor local, nunca internet."""
import hashlib
import io
import json
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

STEP = (b"ISO-10303-21;\r\nHEADER;\r\nFILE_DESCRIPTION(('ViewDefinition [x]'),'2;1');\r\n"
        b"FILE_NAME('a.ifc','2020-01-01T00:00:00',('au'),('org'),'pre','Revit 2021','');\r\n"
        b"FILE_SCHEMA(('IFC4'));\r\nENDSEC;\r\nDATA;\r\nENDSEC;\r\nEND-ISO-10303-21;\r\n")
OUTRO = STEP.replace(b"IFC4", b"IFC2X3").replace(b"Revit 2021", b"ArchiCAD 24")
sha = lambda b: hashlib.sha256(b).hexdigest()


def _zip(nome, dados):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("LEIAME.txt", "x")
        z.writestr(nome, dados)
    return buf.getvalue()


ZIP = _zip("dentro/k.ifc", OUTRO)
ROTAS = {"/x/a.ifc": STEP, "/y/k.zip": ZIP, "/x/b.ifc": OUTRO}


@pytest.fixture
def servidor():
    pedidos = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            pedidos.append(self.path)
            if self.path == "/velho/a.ifc":  # redireção como no ifcwiki
                self.send_response(301)
                self.send_header("Location", "/x/a.ifc")
                self.end_headers()
            elif self.path in ROTAS:
                self.send_response(200)
                self.send_header("Content-Length", str(len(ROTAS[self.path])))
                self.end_headers()
                self.wfile.write(ROTAS[self.path])
            else:
                self.send_error(404)

        def log_message(self, *a):
            pass

    s = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_address[1]}", pedidos
    s.shutdown()
    s.server_close()


def _e(nome, url, **extra):
    d = {"nome": nome, "url": "http://exemplo.invalido/" + url, "licenca": "CC-BY-4.0", "atribuicao": "a",
         "origem": "o", "versao_ou_commit": "v1", "pode_ir_no_git": "sim", "cobre": ["planta"]}
    d.update(extra)
    return d


def _rodar(tmp_path, base, entradas):
    import baixar_corpus
    lista = tmp_path / "lista.json"
    lista.write_text(json.dumps(entradas), encoding="utf-8")
    c, m = tmp_path / "corpus", tmp_path / "manifestos"
    return baixar_corpus.baixar(lista, c, m, base_url_override=base), c, m


def test_baixa_descompacta_e_manifesto_confere(tmp_path, servidor):
    import conferir_corpus
    base, _ = servidor
    erros, c, m = _rodar(tmp_path, base, [_e("a", "x/a.ifc", sha256_esperado=sha(STEP), tamanho_esperado=len(STEP)),
                                          _e("k", "y/k.zip", licenca="KIT", pode_ir_no_git="nao",
                                             arquivo_no_zip="dentro/k.ifc")])
    assert erros == []
    assert (c / "a.ifc").read_bytes() == STEP  # bytes intactos (CRLF)
    assert (c / "k.ifc").read_bytes() == OUTRO and not list(c.glob("*.zip"))
    ma = json.loads((m / "a.json").read_text(encoding="utf-8"))
    assert ma["sha256"] == sha(STEP) and ma["tamanho_bytes"] == len(STEP)
    assert (ma["esquema"], ma["programa_de_origem"]) == ("IFC4", "Revit 2021")
    mk = json.loads((m / "k.json").read_text(encoding="utf-8"))
    assert (mk["esquema"], mk["pode_ir_no_git"], mk["sha256"]) == ("IFC2X3", "nao", sha(OUTRO))
    assert conferir_corpus.conferir(c, m) == []


def test_segue_redirecao(tmp_path, servidor):
    base, _ = servidor
    erros, c, _m = _rodar(tmp_path, base, [_e("a", "velho/a.ifc")])
    assert erros == [] and (c / "a.ifc").read_bytes() == STEP


def test_segunda_execucao_nao_baixa(tmp_path, servidor):
    base, pedidos = servidor
    ent = [_e("a", "x/a.ifc"), _e("k", "y/k.zip", arquivo_no_zip="dentro/k.ifc")]
    assert _rodar(tmp_path, base, ent)[0] == []
    n = len(pedidos)
    assert n >= 2
    assert _rodar(tmp_path, base, ent)[0] == [] and len(pedidos) == n


def test_sha_divergente_e_erro_e_nao_grava(tmp_path, servidor):
    base, _ = servidor
    erros, c, m = _rodar(tmp_path, base, [_e("a", "x/a.ifc", sha256_esperado="0" * 64), _e("b", "x/b.ifc")])
    assert len(erros) == 1 and "a" in erros[0] and "sha256" in erros[0]
    assert not (c / "a.ifc").exists() and not (m / "a.json").exists()
    assert (c / "b.ifc").exists()  # os demais seguem


def test_404_em_ptbr_nao_interrompe(tmp_path, servidor):
    base, _ = servidor
    erros, c, m = _rodar(tmp_path, base, [_e("z", "x/nao-existe.ifc"), _e("b", "x/b.ifc")])
    assert len(erros) == 1 and "z" in erros[0] and "404" in erros[0]
    assert any(p in erros[0].lower() for p in ("falha", "não", "nao", "erro"))
    assert (c / "b.ifc").exists() and (m / "b.json").exists() and not (m / "z.json").exists()


def test_main_codigo_1_com_falha(tmp_path, servidor):
    import baixar_corpus
    base, _ = servidor
    lista = tmp_path / "l.json"
    lista.write_text(json.dumps([_e("z", "x/nao-existe.ifc")]), encoding="utf-8")
    cli = ["--base-url", base, str(lista), str(tmp_path / "c"), str(tmp_path / "m")]
    assert baixar_corpus.main(cli) == 1


def test_cabecalho_step_so_texto(tmp_path):
    import baixar_corpus
    p = tmp_path / "x.ifc"
    p.write_bytes(b"\xef\xbb\xbf" + STEP)  # com BOM
    assert baixar_corpus.cabecalho_step(p) == {"esquema": "IFC4", "programa": "Revit 2021"}
    p.write_bytes(OUTRO.replace(b"\r\n", b"\n").replace(b"FILE_SCHEMA((", b"FILE_SCHEMA(\n("))
    assert baixar_corpus.cabecalho_step(p) == {"esquema": "IFC2X3", "programa": "ArchiCAD 24"}


def test_lista_real_tem_20_e_regras_de_git():
    import conferir_corpus
    arq = RAIZ / "corpus" / "lista.json"
    assert arq.is_file(), "corpus/lista.json ausente"
    lista = json.loads(arq.read_text(encoding="utf-8"))
    assert len(lista) == 20 and len({e["nome"] for e in lista}) == 20
    aceitas = conferir_corpus.LICENCAS_ACEITAS | conferir_corpus.LICENCAS_FORA_DO_GIT
    for e in lista:
        for campo in ("nome", "url", "licenca", "atribuicao", "origem", "versao_ou_commit", "pode_ir_no_git",
                      "cobre", "tamanho_esperado"):
            assert e.get(campo) not in (None, "", []), (e.get("nome"), campo)
        assert e["url"].startswith(("http://", "https://")) and e["licenca"] in aceitas
        assert e["pode_ir_no_git"] in ("sim", "nao")
        if e["tamanho_esperado"] > 1_000_000 or e["licenca"] in conferir_corpus.LICENCAS_FORA_DO_GIT:
            assert e["pode_ir_no_git"] == "nao", e["nome"]
    assert {e["nome"] for e in lista if e["licenca"] == "KIT"}  # os 3 do KIT presentes
    assert sum(e["licenca"] == "KIT" for e in lista) == 3
