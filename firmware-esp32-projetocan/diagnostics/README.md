# Diagnostico Python (Area Limpa)

Esta pasta contem apenas o codigo principal de diagnostico.

## Execucao

No diretorio `firmware-esp32-projetocan`:

`python run_diagnostico.py`

## Entradas padrao

- Logs: `logs/BRP-SEADOO-GTX-2022-300hp/can_log_*.csv`
- Mapa ODX: `../docs/seadoo_odx_can_map.csv`

## Saidas

Geradas em `../docs`:

- `BRP_SEADOO_GTX_2022_300hp_CAN_Analysis.md`
- `BRP_SEADOO_GTX_2022_300hp_CAN_ID_Summary.csv`
- `BRP_SEADOO_GTX_2022_300hp_UDS_Summary.csv`
- `BRP_SEADOO_GTX_2022_300hp_CAN_ID_Timing.csv`

## Legado

Scripts antigos foram movidos para `legacy_python/` para reduzir ruido na raiz.
