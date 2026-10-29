# Python Code Organization

Esta pasta foi reorganizada para separar o scanner principal dos scripts auxiliares.

## Estrutura

- ecm_scanner/
  - App principal de diagnostico (main.py + requirements.txt)
- diagnostics_tools/
  - Scripts de DTC/UDS/atuadores e apoio de diagnostico
  - Inclui `validate_elm327.py` para validar conexao inicial com ELM327 Bluetooth/serial
- license_tools/
  - Scripts de licenca, decriptacao e servidor fake
- seedkey_security/
  - Scripts focados em seed/key e seguranca
- reverse_engineering/
  - Scripts de analise e engenharia reversa geral
- powershell_scripts/
  - Scripts PowerShell auxiliares
- logs/
  - Saidas e logs de patches
- output/
  - Artefatos gerados
- workspace/
  - Arquivos de trabalho temporarios

## Execucao do scanner principal

```powershell
cd c:\Users\johan\Documents\projetoCAN\python-code\ecm_scanner
pip install -r requirements.txt
python main.py
```

## Visualizador K-Line

Para inspecionar visualmente como os bytes/canais mudam ao longo do tempo nos logs Yamaha, use:

```powershell
cd c:\Users\johan\Documents\projetoCAN
python python-code\kline_visualizer.py
```

No app:
- abra um log como `yamaha funcionando.txt` ou `yam.txt`
- ajuste o baud se necessario (padrao `15625`)
- selecione um canal na lista da esquerda
- veja no grafico a serie temporal do valor bruto e do valor base (`v & 0x7F`)
