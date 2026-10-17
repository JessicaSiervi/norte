# IBM Plex Sans e IBM Plex Mono (embutidas no mapa)

Copiadas dos pacotes oficiais do npm (Fontsource), versão 5.3.0, sem alterações:

- `@fontsource/ibm-plex-sans`: https://registry.npmjs.org/@fontsource/ibm-plex-sans/-/ibm-plex-sans-5.3.0.tgz
  - Integridade do pacote (conferida com o registro npm): `sha512-CbE4CbbEEZJX860XyUiRpsksXIQR8Rp2XDva2VO53NJox9tVNtusrysd2x5YkUEY3ErQ66W1IiiQL8/wihhw5w==`
- `@fontsource/ibm-plex-mono`: https://registry.npmjs.org/@fontsource/ibm-plex-mono/-/ibm-plex-mono-5.3.0.tgz
  - Integridade do pacote (conferida com o registro npm): `sha512-eTgnZjZEGk1QtD3ZstF+Vclo2HLAni8YMy34/DxllwZvyz1lR/1RF/xTiAquOBO7MvqBx8D2Ig2WCPMVfdZu7Q==`

Só o subconjunto latino (inclui os acentos do português): Sans 400, 500 e 600; Mono 500.
Licença: SIL Open Font License 1.1 (`OFL.txt` do Sans e `OFL-mono.txt` do Mono, copiadas dos pacotes).

SHA-256 dos arquivos:
- 01d285447409c8a588692162439a038b8cbd7871309ee20267b0d2d91c6e8e22 *ibm-plex-mono-latin-500-normal.woff2
- 3b646991d30055a93a4ecc499713d4347953a74a947ecab435ab72070cbdab0e *ibm-plex-sans-latin-400-normal.woff2
- 0717336fb31fcdcde4b8deb3675bb4a0f7f6d484864afcd6751ac29975962203 *ibm-plex-sans-latin-500-normal.woff2
- 8960851d691c054ed38e259bdcf1a6190d157b4203ed5bb32c632a863fb8ec2f *ibm-plex-sans-latin-600-normal.woff2
- d0283623ef57e722fd0eb688a8041589670c608ab780cd3612d06ba6f153d3fd *OFL.txt
- 23b0a9d0c6d3f140a0b77e483c5cfa6bba574325ef5cb189ed9f2fec4884533f *OFL-mono.txt

O `mapa.py` embute estas fontes no HTML como `data:`, para o mapa não depender de servidor de fontes.
