# SPDX-License-Identifier: AGPL-3.0-or-later
# Teste do instalador com caminhos reais do Brasil (F0-RG-13): pasta com acento e espaço (usuário "João", pasta
# "Residência Casa"). O /D= do NSIS não aceita aspas, então o instalador é aberto pelo PowerShell com a linha de
# comando crua. Instala, abre o app, abre um IFC de nome acentuado, mede o caminho mais longo e desinstala.
# Uso: powershell -NoProfile -ExecutionPolicy Bypass -File test_acento.ps1 -Exe INSTALADOR.exe -Base PASTA -Ifc AMOSTRA.ifc
param([string]$Exe, [string]$Base, [string]$Ifc)
$ErrorActionPreference = 'Continue'  # saída de erro do Python não pode virar exceção do PowerShell
function Falha($msg) { Write-Host "FALHA: $msg"; exit 1 }

$dest = Join-Path $Base 'Usuário João\Residência Casa'
$p = Start-Process -FilePath $Exe -ArgumentList "/S /D=$dest" -Wait -PassThru
if ($p.ExitCode -ne 0) { Falha "instalador saiu com código $($p.ExitCode) em '$dest'" }
$py = Join-Path $dest 'env\python.exe'
$pyw = Join-Path $dest 'app\OpenBIM-Studio.pyw'
if (-not (Test-Path -LiteralPath $pyw)) { Falha "não instalou em '$dest'" }

$env:QT_QPA_PLATFORM = 'offscreen'
$saida = (& $py -I $pyw --selftest 2>&1 | Select-Object -Last 1)
if ("$saida".Trim() -ne 'OK') { Falha "selftest em pasta com acento e espaço: '$saida'" }
Write-Host "   abriu em '$dest'"

# (o PowerShell não distingue maiúsculas: $Ifc e $ifc seriam a mesma variável)
# IFC com acento no nome e na pasta (o ifcopenshell converte o caminho para a página de códigos do sistema?)
$pasta = Join-Path $Base 'Documentos João\Residência'
New-Item -ItemType Directory -Force -Path $pasta | Out-Null
$destIfc = Join-Path $pasta 'Casa Térrea.ifc'
Copy-Item -LiteralPath $Ifc -Destination $destIfc
$cod = 'import sys; sys.path.insert(0, sys.argv[1]); from openbim_app.ifc_summary import count_by_class; print(count_by_class(sys.argv[2]).total)'
$n = (& $py -I -c $cod (Join-Path $dest 'app') $destIfc 2>&1 | Select-Object -Last 1)
if ("$n".Trim() -notmatch '^[1-9][0-9]*$') { Falha "abrir o IFC '$destIfc': '$n'" }
Write-Host "   abriu o IFC acentuado: $n elementos"

# caminho mais longo do que foi instalado (o limite clássico do Windows é 260 caracteres)
$maior = (Get-ChildItem -LiteralPath $dest -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName.Length } | Measure-Object -Maximum).Maximum
$rel = $maior - $dest.Length
$padrao = 'C:\Users\' + ('x' * 20) + '\AppData\Local\Programs\OpenBIM Studio'
Write-Host "   caminho mais longo dentro da instalação: $rel caracteres; com a pasta padrão de um usuário de 20 letras: $($padrao.Length + $rel) (limite 260)"
if ($padrao.Length + $rel -gt 259) { Write-Host "::warning title=caminho longo::a instalação padrão passa de 259 caracteres ($($padrao.Length + $rel))" }

$u = Start-Process -FilePath (Join-Path $dest 'Uninstall.exe') -ArgumentList "/S _?=$dest" -Wait -PassThru
if ($u.ExitCode -ne 0) { Falha "desinstalador saiu com código $($u.ExitCode)" }
Start-Sleep -Seconds 3
foreach ($x in 'env', 'app', 'licenses') { if (Test-Path -LiteralPath (Join-Path $dest $x)) { Falha "sobrou $x depois de desinstalar" } }
Remove-Item -LiteralPath (Join-Path $Base 'Usuário João'), (Join-Path $Base 'Documentos João') -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "   OK: pasta com acento e espaço"
