# SPDX-License-Identifier: AGPL-3.0-or-later
"""`main_mista --parte lote --ifc <arquivo> --apelido <nome>` mede num IFC existente (aqui, uma base gerada por
`gerar_modelo_grande`, nunca IFC de terceiros): mesmo formato de JSON, `base` nulo, `ifc` = apelido (nunca nome nem caminho). Janela em subprocesso, sob xvfb-run."""
import importlib.util
import json
import sys
import tempfile
import traceback
from pathlib import Path

import pytest
import s04_fluxo_aux as aux
from test_s04_v1_mista_oraculo import _ok, _rodar, pular

ESTE = Path(__file__).resolve()
APELIDO = "casaTeste"


def c_ifc(res):
    import gerar_modelo_grande
    import lote
    pasta = Path(tempfile.mkdtemp(prefix="v1b_"))
    ifc = pasta / "arquivo_qualquer.ifc"
    gerar_modelo_grande.gerar(str(ifc), paredes=10)
    saida = pasta / "lote.json"
    res["caminho"] = str(ifc)
    res["ret"] = lote.main_mista([str(saida), "--parte", "lote", "--ifc", str(ifc), "--apelido", APELIDO, "--quantidade", "20", "--rodadas", "1"])
    res["texto"] = saida.read_text(encoding="utf-8")
    res["arquivo"] = json.loads(res["texto"])
    return res


def test_v1b_ifc_grava_apelido_base_nula_e_mesmo_formato():
    if importlib.util.find_spec("obimcore") is None:
        pular("módulo obimcore ausente")
    r = _ok(_rodar("ifc", limite=600, alvo=ESTE))
    a = r["arquivo"]
    assert r["ret"] == a and a["parte"] == "lote" and a["base"] is None and a["ifc"] == APELIDO and a["rodadas"] == 1, sorted(a)
    assert set(a["formas"]) == set(a["controle"]) == {"1", "2", "mista"} and all(len(v) == 1 for v in a["formas"].values())
    assert all("geometria" in rr for rr in a["formas"]["mista"] + a["controle"]["mista"])
    assert all("maior_ms" in rr["resumo"]["fatias"] and "maior_op" in rr["resumo"]["fatias"] for rr in a["formas"]["2"] + a["formas"]["mista"])
    assert "ok" in a["veredito"]
    assert Path(r["caminho"]).name not in r["texto"] and r["caminho"] not in r["texto"], "nem o nome nem o caminho do arquivo vão ao JSON"


def test_v1b_ifc_e_apelido_vao_juntos_e_so_na_parte_lote():
    sys.path.insert(0, str(aux.PASTA))
    import lote
    invalidos = (
        ["--parte", "lote", "--ifc", "x.ifc"],
        ["--parte", "lote", "--apelido", "a"],
        ["--parte", "pesada", "--ifc", "x.ifc", "--apelido", "a"],
    )
    for args in invalidos:
        with pytest.raises(SystemExit):
            lote.main_mista(["/tmp/nao_grava.json", *args])


if __name__ == "__main__":
    import ifcopenshell  # noqa: F401  (antes do obimcore)
    try:
        saida = globals()["c_" + sys.argv[1]]({}, *sys.argv[2:])
    except BaseException:
        saida = {"erro": traceback.format_exc()}
    print("RESULTADO " + json.dumps(saida, ensure_ascii=False, default=str), flush=True)
