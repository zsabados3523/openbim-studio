# F0-RG-19: limpeza de ramos (2026-10-15)

Cartão F0-RG-19 do relatório da revisão geral. Este arquivo é só conferência: **nenhum ramo foi apagado** até o Rafael responder com as próprias palavras. Não altera `v2/` nem `CLAUDE.md`.

Estado do `main` na conferência: `4e8995b0f258571e4a21acec366b34ed3564d9ed`. Ramos remotos conferidos: 102 (main, 49 mesclados, 52 com commits fora do main).

## 1. Ramos já inteiramente dentro do main (49)

Conferido com `git branch -r --merged origin/main` e `git merge-base --is-ancestor` para cada um. Nenhum é ramo de PR aberto (PRs abertos: 101, 103, 105, 108, 109). Para recriar um ramo: `git push origin <hash>:refs/heads/<nome>`.

Recomendação: **apagar com aprovação do Rafael**. Cuidado: `claude/rg-10-trava-runtime` e `claude/rg-11-registro-de-erros` foram mesclados hoje (03:40 e 04:01) e as threads delas podem ainda usar o ramo; apagar por último.

| Ramo | Último commit (hash completo) | Data |
|---|---|---|
| `catalogo-f3` | `51f7c7ba8c75bdda91c7a91b71d3ab4a858fd983` | 2026-10-13 |
| `ci-instalador-condicional` | `4eaa050f83932765c7832a56beb1380e9afcbc38` | 2026-10-14 |
| `claude/project-thread-6k0mor` | `0d5b8306fc450ec42f9f3d47dfde86c79615b0f1` | 2026-10-14 |
| `claude/project-thread-u2i86f` | `275dfc4a2622e5a4a2cdb9b79e7932c3e43da52f` | 2026-10-14 |
| `claude/project-thread-v4a7xa` | `994f84d9f6795b7c87add10a49f387516a8c81d1` | 2026-10-15 |
| `claude/project-thread-xdf8jy` | `5766241fa49f27bc0130ebf359fa799af285a044` | 2026-10-15 |
| `claude/rg-07-deslocamento-cena` | `a7347e1d1aa57126280ab8f8276772935f354f75` | 2026-10-15 |
| `claude/rg-10-trava-runtime` | `bff9ff318fe63c585c2ba83a5729991f1be66d2b` | 2026-10-15 |
| `claude/rg-11-registro-de-erros` | `0d41aee5591aed8aa1c706b50536d75a20919690` | 2026-10-15 |
| `claude/rg-13-appimage` | `7abc7b1f280a9c6a96d1fabcdada39c8a17348dc` | 2026-10-15 |
| `claude/s02-t25-windows-incremental` | `bb5ba41ce517505721d0e4ce0dfca7253a474ad9` | 2026-10-15 |
| `entrevista-s09` | `c52adb1e5c9c9788846666b49456f8d16f873713` | 2026-10-12 |
| `estado-s04` | `b234f04ad33a1ecfe29539ef69cfb6370a48acfe` | 2026-10-12 |
| `estado-s04b` | `0ae811360077755eba3b39674155129b334ca7b8` | 2026-10-12 |
| `fix-instalador-poda` | `0002446a9ae521fe1094c326f5b82b47e4a2287b` | 2026-10-14 |
| `fix-tempo-selecao` | `29a04be3fd490d9178f0fb8636f33b7c8514659d` | 2026-10-12 |
| `pesquisa-ferramentas` | `ad05f1f2ccc596a830f24d7e3907ea014f175b36` | 2026-10-12 |
| `po-decisoes-s09` | `5d21668db2c8d1688e8c404f26e6f1a345391dee` | 2026-10-14 |
| `regra-lote-opus-aplicada` | `d0aa9984384be6c3caaacbefeaff8e3f138db61a` | 2026-10-12 |
| `s03-t06b` | `a20b5e9269fbfb976beaebada45a8bda89dfa096` | 2026-10-12 |
| `s04-t01` | `0095497ab4c1ab2bd0bcb4d988eb295b26cefa8a` | 2026-10-12 |
| `s04-t01-trava-win` | `9302ecda25b11934e62efea917c1d3246563f509` | 2026-10-12 |
| `s04-t02` | `025b8073109d3d9b6d8ca12c1dccddadb25015f6` | 2026-10-12 |
| `s04-t02b` | `dc14ac1860a1b8145a5029fb3308e638727eeb4b` | 2026-10-12 |
| `s04-t03` | `86317bd5a412f210e2164aa66570fca3035d9df4` | 2026-10-12 |
| `s04-t04` | `cf57dd8e1fefa37954dfcd91971d4192a927b20a` | 2026-10-12 |
| `s04-t04c` | `79300bfa4fbe70ff8eef4955d00e353f81394f0d` | 2026-10-12 |
| `s04-t05` | `81f9f4a67068b54a42271717ad6d9a7622433568` | 2026-10-13 |
| `s04-t06` | `08b4f6d73679a3584de4620d17e5873d817b814b` | 2026-10-13 |
| `s04-t06b` | `67669e19a87c2dec12b8f6d25c671360df2c038f` | 2026-10-13 |
| `s04-t07` | `266bee98b0c30a630adf8f1d0c19e826697fe1d7` | 2026-10-13 |
| `s04-t07b` | `762d9a995a73adfd936c9dd114d05fbebd00a8ad` | 2026-10-13 |
| `s04-t08` | `f44e7cef052befd39820c2fa6d5d4ceee2ff6db5` | 2026-10-13 |
| `s04-t09` | `472e2ec3f1e1ee34d121b15d85cb9776fbccaa33` | 2026-10-13 |
| `s04-t09-oraculo` | `6c4b95d4a942fd5049f1db6b63922992e4a6be55` | 2026-10-13 |
| `s04-t10` | `5c5a6af7e70c8611e27471771df4741131186be5` | 2026-10-13 |
| `s04-t10-oraculo` | `2c93a1ba358867d2df95a0a5b0318ab2ee96e93e` | 2026-10-13 |
| `s04-t10c` | `0a3324df3b3558aeb081e7bbcb07fe7864d6b5b9` | 2026-10-13 |
| `s04-t11` | `c8d1ee7b921a3d0ce14843cd585a9636b24b3573` | 2026-10-13 |
| `s04-t11-oraculo` | `0912a48cf06a8dd4bf589245589c10873fbcb0ba` | 2026-10-13 |
| `s04-t11b` | `1fa501b1ccaa53b16e9fc07bcfbd5d569fec4482` | 2026-10-13 |
| `s04-t11c` | `16ce95f1e679c51f9021d0c37fc9581cf2eef24f` | 2026-10-14 |
| `s04-t12` | `3174632aac2cb1da1c75bba00fc40663e0c754ca` | 2026-10-15 |
| `s04-t13` | `0f2549cc66ebdb3c42f10842f27259b2009fa422` | 2026-10-13 |
| `s04-t13-oraculo` | `b876c35a966edd3b74572460536d1efd3008a316` | 2026-10-13 |
| `s04-t14a` | `304f5fa1defbc650829bf20b65406b92eec66a7c` | 2026-10-14 |
| `s04-t14b` | `f2ffe250e46ef4df57d445fc146a399ffee7ca83` | 2026-10-14 |
| `s04-t16` | `27eea6f709a89e0ba087925b5f5df9e47e3004e5` | 2026-10-13 |
| `s04-t16-oraculo` | `e27dc51b18bc6d920c766442b8c715ed01e57b22` | 2026-10-13 |

## 2. Ramos com commits fora do main (52)

Método: para cada ramo, comparei os arquivos que ele mudou com os do main. "Igual" = arquivo idêntico no main; "mudou" = o main já seguiu em frente (o arquivo tem versão mais nova); "ausente" = o arquivo não existe no main. Como o projeto mescla com compressão de commits, o aviso do Git de "não mesclado" não prova que o trabalho foi perdido. Para os ramos antigos (S01 a S03, aceitas pelo Rafael), "mudou" é o esperado; não li o conteúdo de cada um linha a linha.

| Ramo | Último commit | Data | Arquivos (igual/mudou/ausente) | O que tem de não mesclado | Recomendação |
|---|---|---|---|---|---|
| `catalogo-editar` | `ae9d53f06b714cc54cc4f6f561b049251011d229` | 2026-10-12 | 0/1/0 | 1 commit: títulos de grupo no desenho da caixa de ferramentas (docs/design/catalogo-ferramentas-f1-f2.md); não está no main | Recuperar (o Rafael decide se vale) |
| `claude/project-thread-0om4w2` | `a5353a0fa24f71c74fc609569bd7f3ba0b1ae7a9` | 2026-10-15 | 0/0/1 | PR 101 aberto (ADR-004 rascunho) | Manter |
| `claude/project-thread-hjrpmx` | `4bcb28a3debe41f9bd9a9ad40d00d86778678f41` | 2026-10-14 | 0/2/0 | PR 96 fechado sem mesclar (rascunho); o PR 95 fez o mesmo e foi mesclado | Apagar com aprovação do Rafael |
| `claude/project-thread-lx8h49` | `baa3c0aa7eb8b15fe742a8a3f738bc7dc55feaf4` | 2026-10-15 | 0/0/1 | PR 108 aberto (revisão Opus RG-07) | Manter |
| `claude/project-thread-y9n8vj` | `ea6c404954c9519108b4ef7c1d8709a808fd9586` | 2026-10-15 | 36/0/0 | PR 97 já mesclado; os 36 arquivos do ramo são idênticos aos do main (só falta o ponteiro, por mesclagem com compressão) | Apagar com aprovação do Rafael |
| `claude/rg-11-mensagens-abertura` | `dd6769545d60139bab46239060edec8478b0ee37` | 2026-10-15 | 0/2/0 | PR 109 aberto | Manter |
| `claude/rg-13-instalador` | `9028146c24c8435a3edb3062cf283dee7d8eaa44` | 2026-10-15 | 0/2/1 | PR 105 aberto | Manter |
| `claude/rg03-testes-pulados` | `19877c71d3cf32dbaca40b42c009408ed8c59835` | 2026-10-15 | 0/15/1 | PR 103 aberto | Manter |
| `estado-lote7` | `6c7eab98300b8e521229377d527bd2fbda2d144a` | 2026-10-12 | 0/42/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `estado-lote8` | `93d339fc6fe1057901f0cec7b704a721c1e28dd2` | 2026-10-12 | 0/42/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `estado-s03-relatorio` | `ed1cce79ea9748b74665271673644804ffbf13d4` | 2026-10-12 | 1/1/1 | 1 commit: PROPOSTA_CLAUDE_MD.md (texto para o Rafael colar no CLAUDE.md); esse arquivo não existe no main | Manter (decisão do Rafael sobre o CLAUDE.md) |
| `estado-sessao4` | `22d6fb7faddabaa3f8a4fa7c9163680d96159ba6` | 2026-10-11 | 0/33/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `estado-t07` | `1634c3828d4fe5f525b0afdca681ba4b43b6bc4e` | 2026-10-12 | 0/40/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `estado-t08a` | `79687906bf132f5aa550774ed1bb58c96eb87366` | 2026-10-12 | 0/43/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `fecha-s02` | `0c8a993f6a797b771b8aebffa75c188aff9eacc2` | 2026-10-11 | 0/33/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `fix-locale` | `c71cfd628e0778d4f786effe47857fe12e48b593` | 2026-10-11 | 0/40/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `fix-nome-referencia` | `7ae5b8a00a9442d2d1288e8df5c443b878a785b9` | 2026-10-12 | 0/40/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `lote2-resultado` | `51029b957a8b77ee62c7eb5acf837a3d9276e109` | 2026-10-11 | 0/39/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `lote3-correcoes` | `36ae99e254f640717312b6984e573a4652864891` | 2026-10-11 | 0/33/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `lote5-estado` | `69eb48b2b139eba8e07c28c269f1a737016d22a6` | 2026-10-11 | 0/41/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `lote6-estado` | `f74b4e2463cd562fef08fc395d4922be001a2d80` | 2026-10-12 | 0/41/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `rascunho-t08` | `acb3444f03fe1d53639c96e5277a0e9a2d7b9b34` | 2026-10-12 | 0/42/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s02-t24` | `8ec4b1a76c7b6244ef2196118ff2335b8df78c1d` | 2026-10-11 | 0/39/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-lote4` | `670aeeb179be4cef5fd2f388c3b1f79bf1d05881` | 2026-10-11 | 0/40/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-lote5` | `6da0a1d0523eb9ab5ec7a3d1d59192bd44126efd` | 2026-10-11 | 0/41/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t01` | `8c69d0ddadc2610e10059bf40427d1103b8aad6b` | 2026-10-11 | 0/34/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t02` | `81c8afb11bb79939b794f6cbe1d4cad84684dc95` | 2026-10-11 | 0/38/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t03` | `c810a986dbed55cb48b5fcc9b0d82feee1476c7e` | 2026-10-11 | 0/39/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t04` | `9bdb33d50545b0a2a5471c1c3be84ff7e4d83337` | 2026-10-11 | 0/39/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t05-a` | `9ddedb227ffadf78ad29603b9dd019fc7ce975cf` | 2026-10-12 | 0/43/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t05-b` | `7418355decb82f5878f58df8d61916e83e3b9f98` | 2026-10-12 | 0/44/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t05-p0` | `6911bc5b1bc640f3481f0546669b443d3e9f4aeb` | 2026-10-12 | 0/43/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t05-teste-memoria` | `7e49c0a8d30d21fed0b9bfffb3d183535790a300` | 2026-10-12 | 0/43/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t06` | `a982a15d2a88401f43bc57405e74620dd4cb1e80` | 2026-10-11 | 0/40/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t08-0` | `604c43ee83059849e20e3ff92ff8bd4cfefecd68` | 2026-10-12 | 0/42/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t08-0b` | `80ce5b28f1f86dbeb291f729119cb094a59fc5d7` | 2026-10-12 | 0/43/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t08-a` | `094cfedc73a42365bd6db8384ff6a3191c12dc2f` | 2026-10-12 | 0/42/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t08-b1` | `a3a64720e4e2782e976cc371010a97def284043c` | 2026-10-12 | 0/43/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t08-b2` | `1419cdd274278a758b4b465f98cb7872a4c51eae` | 2026-10-12 | 0/43/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t08-c` | `b5bdf0f26c5002f9ff30b17b0265265e0be79b37` | 2026-10-12 | 0/43/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t08-d` | `d0a6b3489fe98df7e341ac07d27597a727ac425a` | 2026-10-12 | 0/43/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t08-e` | `acb3444f03fe1d53639c96e5277a0e9a2d7b9b34` | 2026-10-12 | 0/42/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t25` | `5297a7b465d28b20fc9d5ed0b4b5dab23b360519` | 2026-10-11 | 0/40/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t26` | `6caa50a653cf9bb68b231a6ce16c15d8a5940f4d` | 2026-10-12 | 0/43/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t26-oraculo` | `84a298d5c4a51b55bb2c095bc47787bcf7832127` | 2026-10-12 | 0/45/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s03-t26b` | `1a1aeca72f5d7cbb740661dc159a039b0390b88f` | 2026-10-12 | 0/40/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `s04-t14` | `7930e052183aa5087a74195c5c5fc73b2c80640e` | 2026-10-13 | 0/2/2 | 1 commit: oráculo da janela do fluxo B (testes e CI); não está no main; já incluído no ramo s04-t14c | Manter (S04 pausada) |
| `s04-t14c` | `66ceaddb85c5eb1104c1b30cb0f7d2dceaf2f9a1` | 2026-10-14 | 1/9/4 | 4 commits: janela do fluxo B em C++ (T14c), seu oráculo e ajuste; trabalho da S04 ainda fora do main | Manter (S04 pausada); recuperar quando a S04 voltar |
| `sonda-3b` | `96b536be2961fc3356eb2aedc8f94f20a23f99be` | 2026-10-11 | 0/39/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `t11-compactacao-xz` | `8d62011ebdc97c5c26466c403f6f61c44834a86e` | 2026-10-11 | 0/44/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `t11-instalador-windows` | `471c0470ce86a1819e074c143c12064f7cb91a24` | 2026-10-10 | 0/44/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |
| `t13-t14-metricas` | `6c452fd81884046659729c02210011ecf998abc3` | 2026-10-11 | 0/47/0 | Ramo antigo de trabalho das fatias S01 a S03 ou de estado; o main já tem versões mais novas dos arquivos (mesclagem com compressão) | Apagar com aprovação do Rafael |

## 3. Resumo

- Manter: 5 ramos de PR aberto, `estado-s03-relatorio`, `s04-t14`, `s04-t14c`.
- Recuperar: `catalogo-editar`.
- Apagar com aprovação: os demais (43), mais os 49 já mesclados.
- Apagados até agora: nenhum.
