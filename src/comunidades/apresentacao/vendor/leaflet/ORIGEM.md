# Leaflet 1.9.4 (embutido no mapa)

Copiado do pacote oficial do npm: https://registry.npmjs.org/leaflet/-/leaflet-1.9.4.tgz

- Integridade do pacote (conferida com o registro npm): `sha512-nxS1ynzJOmOlHp+iL3FyWqK89GtNL8U8rvlMOsQdTTssxZwCXh8N2NB3GDQOL+YR3XnWyZAxwQixURb+FA74PA==`
- Arquivos: `dist/leaflet.js`, `dist/leaflet.css` e `LICENSE` (BSD 2-Clause), sem alterações.
- SHA-256 dos arquivos:
  - db49d009c841f5ca34a888c96511ae936fd9f5533e90d8b2c4d57596f4e5641a *leaflet.js
  - a7837102824184820dfa198d1ebcd109ff6d0ff9a2672a074b9a1b4d147d04c6 *leaflet.css
  - 53e8dc25862014e4324741ca18fbe3611e11d42ef69f59f86ea8c5389647d4cb *LICENSE

O `mapa.py` embute estes arquivos no HTML gerado, para o mapa não depender de CDN.
