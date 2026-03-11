# Brands submission (Home Assistant)

Este pacote prepara os arquivos para o repositório oficial de marcas do Home Assistant:
`https://github.com/home-assistant/brands`

## Arquivos prontos

Copie estes arquivos para o path abaixo no repositório `home-assistant/brands`:

Path destino:
`custom_integrations/tarifas_energia_brasil/`

Arquivos:
- `docs/brands_submission/tarifas_energia_brasil/icon.png` (256x256)
- `docs/brands_submission/tarifas_energia_brasil/icon@2x.png` (512x512)
- `docs/brands_submission/tarifas_energia_brasil/logo.png` (256x256)
- `docs/brands_submission/tarifas_energia_brasil/logo@2x.png` (512x512)

## Titulo sugerido para PR

`Add branding for tarifas_energia_brasil custom integration`

## Corpo sugerido para PR

```md
## Proposed change

Add branding assets for the custom integration `tarifas_energia_brasil`.

## Asset checklist

- [x] `icon.png` (256x256)
- [x] `icon@2x.png` (512x512)
- [x] `logo.png` (256x256)
- [x] `logo@2x.png` (512x512)

## Notes

- Domain: `tarifas_energia_brasil`
- Repository: `https://github.com/diogocaseca/ha_tarifas_energia_brasil`
```

## Observacao

Sem merge no `home-assistant/brands`, a tela nativa de Integracoes do HA pode continuar com placeholder, mesmo com o icone correto no HACS.
