# SPDX-License-Identifier: AGPL-3.0-or-later
"""Diário de transações e recuperação depois da queda (ADR-002 §4.4, §4.7 e §4.8). Sem Qt, sem `obimcore`.
Uma linha por registro: `<crc32 8 hex> <JSON compacto>\\n`, CRC sobre os bytes UTF-8 do JSON. Registros autossuficientes: desfazer e refazer
levam as mesmas operações do passo. Confirmado = linha escrita (sem buffer do Python); `fsync` cerca de 2 s depois, ao sincronizar e ao fechar."""
import datetime
import hashlib
import json
import math
import os
import re
import shutil
import sys
import threading
import uuid
import zlib
from pathlib import Path

from openbim_app.transacao import HistoricoQuebrado

_LINHA = re.compile(rb"([0-9a-f]{8}) (.+)")
_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "openbim-studio/lado-id")
_FSYNC_S = 2.0


class OperacaoNaoSerializavel(ValueError):
    """Operação com valor que não vira JSON (bytes, NaN, infinito ou chave que não é texto)."""


def _hora():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _jsonable(v):
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if not isinstance(k, str):
                raise OperacaoNaoSerializavel(f"chave que não é texto: {k!r}")
            out[k] = _jsonable(x)
        return out
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, float):
        if not math.isfinite(v):
            raise OperacaoNaoSerializavel("NaN ou infinito")
        return v
    if v is None or isinstance(v, (str, int, bool)):
        return v
    raise OperacaoNaoSerializavel(f"tipo que não vira JSON: {type(v).__name__}")


def _codificar_op(op):
    out = {}
    for k, v in op.items():
        if k == "inverses" and isinstance(v, dict):
            out[k] = [[int(i), [[idx, _jsonable(x)] for idx, x in data]] for i, data in v.items()]
        else:
            out[k] = _jsonable(v)
    return out


def codificar_ifc(ops):
    lista = [_codificar_op(op) for op in ops]
    json.dumps(lista, allow_nan=False)
    return lista


def decodificar_ifc(lista):
    out = []
    for op in lista:
        novo = {}
        for k, v in op.items():
            if k == "inverses" and isinstance(v, list):
                novo[k] = {int(i): [[int(idx), x] for idx, x in data] for i, data in v}
            else:
                novo[k] = v
        out.append(novo)
    return out


def pasta_base():
    if os.environ.get("OBIM_PASTA_LOCAL"):
        return Path(os.environ["OBIM_PASTA_LOCAL"])
    if sys.platform == "win32":
        return Path(os.environ["LOCALAPPDATA"]) / "OpenBIMStudio"
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg) if xdg else Path.home() / ".local" / "share") / "OpenBIMStudio"


def pasta_projeto(lado_id):
    return pasta_base() / "projetos" / str(lado_id)


def lado_id_de(arquivo, ifc_sha256):
    for ps in arquivo.by_type("IfcPropertySet"):
        if ps.Name != "OBIM_Projeto":
            continue
        for prop in ps.HasProperties or ():
            if prop.Name == "LadoId":
                valor = getattr(prop.NominalValue, "wrappedValue", None)
                if valor:
                    return str(valor)
    return str(uuid.uuid5(_NAMESPACE, ifc_sha256))


def _sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _avisar_parar(avisos, n, motivo):
    avisos.append(f"linha {n + 1} do diário {motivo}; os registros seguintes foram ignorados")


def ler_diario(caminho):
    """Devolve `(registros, avisos)`; nunca aplica meio registro."""
    try:
        bruto = Path(caminho).read_bytes()
    except FileNotFoundError:
        return [], ["diário não encontrado; nada foi aplicado"]
    avisos = []
    linhas = bruto.split(b"\n")
    if bruto and not bruto.endswith(b"\n"):
        avisos.append("última linha do diário está cortada e foi ignorada")
        linhas = linhas[:-1]
    elif linhas and linhas[-1] == b"":
        linhas = linhas[:-1]
    regs = []
    for n, linha in enumerate(linhas):
        m = _LINHA.fullmatch(linha)
        if not m:
            _avisar_parar(avisos, n, "não está no formato")
            break
        if int(m[1], 16) != zlib.crc32(m[2]) & 0xFFFFFFFF:
            _avisar_parar(avisos, n, "tem soma de conferência errada")
            break
        try:
            reg = json.loads(m[2].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            _avisar_parar(avisos, n, "não contém JSON válido")
            break
        if not isinstance(reg, dict) or not isinstance(reg.get("seq"), int):
            _avisar_parar(avisos, n, "não é um registro válido")
            break
        if not regs and reg.get("tipo") != "base":
            _avisar_parar(avisos, n, "não começa pelo registro base")
            break
        if regs and reg.get("tipo") not in ("transacao", "desfazer", "refazer"):
            _avisar_parar(avisos, n, "tem tipo desconhecido")
            break
        if regs and reg["seq"] != regs[-1]["seq"] + 1:
            _avisar_parar(avisos, n, "tem buraco na numeração")
            break
        regs.append(reg)
    if not regs or regs[0].get("tipo") != "base":
        regs = []
        avisos.append("diário sem registro base inteiro; nada foi aplicado")
    return regs, avisos


def _aplicar_lado(lateral, ops, avanco):
    for c, i, antigo, novo in (ops if avanco else reversed(ops)):
        lateral._repor(c, i, novo if avanco else antigo)


def recuperar(ifc_caminho, diario_caminho, lateral=None):
    """Abre o IFC e reaplica o diário; nunca grava na pasta do IFC (P5)."""
    import ifcopenshell
    from ifcopenshell.file import Transaction

    from openbim_app.lateral import Lateral

    regs, avisos = ler_diario(diario_caminho)
    arquivo = ifcopenshell.open(str(ifc_caminho))
    lat = lateral if lateral is not None else Lateral()
    if not regs:
        return arquivo, lat, avisos
    base = regs[0]
    if base.get("ifc_sha256") != _sha256(ifc_caminho):
        avisos.append("o diário é de outro arquivo base (sha256 diferente); nada foi aplicado")
        return arquivo, lat, avisos
    obim_sha = base.get("obim_sha256")
    if obim_sha is not None:
        if lateral is None or hashlib.sha256(lateral.canonico()).hexdigest() != obim_sha:
            avisos.append("o diário é de outro arquivo lateral (obim_sha256 diferente); nada foi aplicado")
            return arquivo, lat, avisos
    elif lateral is not None and lateral.canonico() != b"{}":
        avisos.append("o diário não tem lateral, mas foi informado lateral com dados; nada foi aplicado")
        return arquivo, lat, avisos
    for reg in regs[1:]:
        tr = Transaction(arquivo)
        tr.operations = decodificar_ifc(reg.get("ifc") or [])
        desfazer = reg.get("tipo") == "desfazer"
        (tr.rollback if desfazer else tr.commit)()
        _aplicar_lado(lat, reg.get("lado") or [], not desfazer)
    return arquivo, lat, avisos


class Diario:
    def __init__(self, caminho, lado_id, base):
        self.caminho, self.lado_id = Path(caminho), lado_id
        self._seq, self._timer, self._fechado, self._quebrado = 0, None, False, False
        self._lock = threading.RLock()
        self._erro_fsync = None
        self._base = dict(base)
        self._f = open(self.caminho, "w+b", buffering=0)
        try:
            self._gravar(base)
        except BaseException:
            self._f.close()
            raise
        self._seq = 1

    @classmethod
    def abrir(cls, lado_id, ifc_caminho, obim_sha256=None):
        caminho = pasta_projeto(lado_id) / "diario" / "diario.obimlog"
        caminho.parent.mkdir(parents=True, exist_ok=True)
        base = {
            "v": 1, "seq": 0, "tipo": "base", "hora": _hora(),
            "ifc_sha256": _sha256(ifc_caminho), "ifc_tamanho": os.stat(ifc_caminho).st_size,
            "ifc_caminho": str(ifc_caminho), "obim_sha256": obim_sha256, "lado_id": lado_id,
        }
        if not caminho.exists():
            return cls(caminho, lado_id, base)

        tmp = caminho.with_name(caminho.name + ".tmp")
        try:
            d = cls(tmp, lado_id, base)
            try:
                os.fsync(d._f.fileno())
            finally:
                d._f.close()
        except BaseException:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            raise

        desc = caminho.parent / "diario-descartado.obimlog"
        n = 1
        while desc.exists():
            desc = caminho.parent / f"diario-descartado-{n}.obimlog"
            n += 1

        try:
            try:
                os.link(caminho, desc)
            except OSError:
                shutil.copy2(caminho, desc)
            os.replace(tmp, caminho)
        except BaseException:
            if desc.exists():
                try:
                    desc.unlink()
                except OSError:
                    pass
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
            raise

        d.caminho = caminho
        try:
            d._f = open(caminho, "r+b", buffering=0)
            d._f.seek(0, os.SEEK_END)
        except BaseException:
            if getattr(d, "_f", None) and not d._f.closed:
                d._f.close()
            raise
        return d

    @classmethod
    def continuar(cls, caminho, lado_id, base, ultimo_seq):
        caminho = Path(caminho)
        d = cls.__new__(cls)
        d.caminho, d.lado_id = caminho, lado_id
        d._seq = ultimo_seq + 1
        d._timer, d._fechado, d._quebrado = None, False, False
        d._lock = threading.RLock()
        d._erro_fsync = None
        d._base = dict(base)
        d._f = open(caminho, "r+b", buffering=0)
        pos = 0
        linhas = d._f.read().splitlines(keepends=True)
        for linha in linhas:
            if not linha.endswith(b"\n"):
                break
            m = _LINHA.fullmatch(linha.rstrip(b"\r\n"))
            if not m or int(m[1], 16) != zlib.crc32(m[2]) & 0xFFFFFFFF:
                break
            try:
                reg = json.loads(m[2].decode("utf-8"))
            except Exception:
                break
            if not isinstance(reg, dict) or not isinstance(reg.get("seq"), int):
                break
            pos += len(linha)
            if reg.get("seq") == ultimo_seq:
                break
        d._f.truncate(pos)
        d._f.seek(pos)
        if pos < sum(len(l) for l in linhas):
            try:
                os.fsync(d._f.fileno())
            except OSError:
                pass
        return d

    def _linha(self, reg):
        raw = json.dumps(reg, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        return b"%08x " % zlib.crc32(raw) + raw + b"\n"

    def _escrever(self, dados):
        vistos = 0
        while vistos < len(dados):
            n = self._f.write(dados[vistos:])
            if not n:
                raise OSError("escrita sem avanço no diário")
            vistos += n

    def _cortar(self, pos):
        try:
            self._f.truncate(pos)
            self._f.seek(pos)
        except BaseException:
            self._quebrado = True
            raise

    def _gravar(self, reg):
        self._escrever(self._linha(reg))

    def anotar(self, tipo, ifc, lado):
        if tipo not in ("transacao", "desfazer", "refazer"):
            raise ValueError(f"tipo de registro inválido: {tipo!r}")
        ponto, falha = os.environ.get("OBIM_S05_MORRER_EM"), os.environ.get("OBIM_S05_FALHA_EM")
        if falha == "anotar_antes":
            raise OSError("falha simulada antes de anotar no diário")
        if ponto == "anotar_antes":
            os._exit(86)
        with self._lock:
            if self._fechado:
                raise ValueError("diário já fechado")
            if self._erro_fsync is not None:
                err = self._erro_fsync
                self._erro_fsync = None
                raise err
            if self._quebrado:
                raise HistoricoQuebrado("diário quebrado; reabra pela recuperação")
            reg = {"v": 1, "seq": self._seq, "tipo": tipo, "hora": _hora(),
                   "ifc": _jsonable(ifc), "lado": _jsonable(list(lado))}
            linha = self._linha(reg)
            pos = self._f.tell()
            try:
                if ponto == "anotar_meio" or falha == "anotar_meio":
                    self._escrever(linha[:max(1, len(linha) // 2)])
                    if falha == "anotar_meio":
                        raise OSError("falha simulada no meio de anotar no diário")
                    os._exit(86)
                self._escrever(linha)
            except BaseException:
                try:
                    self._cortar(pos)
                except BaseException:
                    self._quebrado = True
                raise
            if ponto == "anotar_depois":
                os._exit(86)
            self._seq += 1
            self._agendar()

    def _agendar(self):
        with self._lock:
            if self._fechado or self._timer is not None:
                return
            self._timer = threading.Timer(_FSYNC_S, self._acordar)
            self._timer.daemon = True
            self._timer.start()

    def _acordar(self):
        with self._lock:
            self._timer = None
            if self._fechado or self._quebrado:
                return
            try:
                os.fsync(self._f.fileno())
            except BaseException as e:
                self._quebrado = True
                self._erro_fsync = e

    def sincronizar(self):
        with self._lock:
            if self._fechado:
                return
            if self._erro_fsync is not None:
                err = self._erro_fsync
                self._erro_fsync = None
                raise err
            if self._quebrado:
                raise HistoricoQuebrado("diário quebrado; reabra pela recuperação")
            try:
                os.fsync(self._f.fileno())
            except BaseException:
                if self._timer is not None:
                    self._timer.cancel()
                    self._timer = None
                self._quebrado = True
                raise

    def fechar(self):
        with self._lock:
            if self._fechado:
                return
            self._fechado = True
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            err = self._erro_fsync
            self._erro_fsync = None
            try:
                if not self._quebrado and err is None:
                    os.fsync(self._f.fileno())
            finally:
                self._f.close()
            if err is not None:
                raise err

    @property
    def ultimo_seq(self):
        with self._lock:
            return self._seq - 1

    def zerar(self, seq, *, ifc_caminho=None, obim_sha256=None):
        with self._lock:
            if self._fechado:
                raise ValueError("diário já fechado")
            if self._erro_fsync is not None:
                err = self._erro_fsync
                self._erro_fsync = None
                raise err
            if self._quebrado:
                raise HistoricoQuebrado("diário quebrado; reabra pela recuperação")
            if seq <= self._base.get("seq", 0):
                return
            try:
                self._f.seek(0)
                linhas = self._f.read().splitlines(keepends=True)
                if not linhas or not linhas[0].endswith(b"\n"):
                    raise HistoricoQuebrado("registro base corrompido")
                m0 = _LINHA.fullmatch(linhas[0].rstrip(b"\r\n"))
                if not m0 or int(m0[1], 16) != zlib.crc32(m0[2]) & 0xFFFFFFFF:
                    raise HistoricoQuebrado("registro base corrompido")
                base = json.loads(m0[2].decode("utf-8"))
            except BaseException:
                self._quebrado = True
                raise
            base["seq"] = seq
            if ifc_caminho is not None:
                base["ifc_caminho"] = str(ifc_caminho)
                base["ifc_sha256"] = _sha256(ifc_caminho)
                base["ifc_tamanho"] = os.stat(ifc_caminho).st_size
            if obim_sha256 is not None:
                base["obim_sha256"] = obim_sha256
            linhas_manter = [self._linha(base)]
            max_seq = seq
            for linha in linhas[1:]:
                if not linha.endswith(b"\n"):
                    break
                m = _LINHA.fullmatch(linha.rstrip(b"\r\n"))
                if not m or int(m[1], 16) != zlib.crc32(m[2]) & 0xFFFFFFFF:
                    break
                try:
                    reg = json.loads(m[2].decode("utf-8"))
                except Exception:
                    break
                r_seq = reg.get("seq", 0)
                if r_seq > seq:
                    linhas_manter.append(linha)
                    if r_seq > max_seq:
                        max_seq = r_seq
            novo = b"".join(linhas_manter)
            tmp = self.caminho.with_name(self.caminho.name + ".tmp")
            trocou = False
            f_antigo_fechado = False
            f_tmp = None
            try:
                f_tmp = open(tmp, "w+b", buffering=0)
                try:
                    vistos = 0
                    while vistos < len(novo):
                        n = f_tmp.write(novo[vistos:])
                        if not n:
                            raise OSError("escrita sem avanço no diário")
                        vistos += n
                    os.fsync(f_tmp.fileno())
                finally:
                    f_tmp.close()
                    f_tmp = None

                self._f.close()
                f_antigo_fechado = True

                os.replace(tmp, self.caminho)
                trocou = True

                if sys.platform != "win32":
                    fd_pasta = os.open(self.caminho.parent, os.O_RDONLY)
                    try:
                        os.fsync(fd_pasta)
                    finally:
                        os.close(fd_pasta)

                self._f = open(self.caminho, "a+b", buffering=0)
                self._f.seek(0, os.SEEK_END)
            except BaseException:
                if f_tmp is not None and not f_tmp.closed:
                    try:
                        f_tmp.close()
                    except BaseException:
                        pass
                if not trocou:
                    if tmp.exists():
                        try:
                            tmp.unlink()
                        except OSError:
                            pass
                    if f_antigo_fechado:
                        try:
                            self._f = open(self.caminho, "a+b", buffering=0)
                            self._f.seek(0, os.SEEK_END)
                        except BaseException:
                            self._quebrado = True
                    else:
                        try:
                            self._f.seek(0, os.SEEK_END)
                        except BaseException:
                            pass
                else:
                    self._quebrado = True
                raise

            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._base = base
            self._seq = max(self._seq, max_seq + 1)
