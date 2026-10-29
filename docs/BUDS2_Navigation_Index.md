# 📚 BUDS2 Reverse Engineering - Índice de Navegação

**Última atualização:** 09/03/2026  
**Documentos:** 5 + Scripts + Dados  
**Tempo de Leitura Total:** 90 minutos

---

## 🗂️ Estrutura Completa

```
firmware-esp32-projetocan/
│
├── 📄 docs/ [DOCUMENTAÇÃO TÉCNICA]
│   ├── ✅ BUDS2_Executive_Summary.md
│   │   └── 📋 Resumo executivo (LEIA PRIMEIRO!)
│   │       ├── Arquivos criados hoje
│   │       ├── Próximos passos
│   │       └── Checklist de progresso
│   │
│   ├── ✅ BUDS2_Quick_Start_Today.md
│   │   └── 🚀 Guia prático "comece em 2 horas"
│   │       ├── 5 passos simples
│   │       ├── Troubleshooting
│   │       └── Árvore de decisão
│   │
│   ├── ✅ BUDS2_ReversEngineering_Analysis.md
│   │   └── 🔍 Análise estrutural completa
│   │       ├── Componentes descobertos
│   │       ├── Mapeamento de arquivos
│   │       ├── Dependências
│   │       └── Quick wins
│   │
│   ├── ✅ BUDS2_Technical_ReverseEngineering_Plan.md
│   │   └── 📐 Plano técnico detalhado
│   │       ├── Achados críticos
│   │       ├── Plano de 5 fases
│   │       ├── Arquitetura
│   │       └── Stack recomendado
│   │
│   └── 📁 BUDS2_Analysis/ [DADOS ESTRUTURADOS]
│       └── buds2_inventory.json
│           └── Inventory de componentes
│
├── 💻 python-code/ [SCRIPTS PRONTOS]
│   ├── ✅ bruteforce_seedkey_aggressive.py (NOVO!)
│   │   └── 🎯 Execute este PRIMEIRO
│   │       ├── Full brute-force
│   │       └── Export JSON resultados
│   │
│   ├── analyze_seed_key.py
│   ├── test_seed_key_dll.py
│   ├── fake_license_server.py
│   ├── crack_seed_key_v2.py
│   └── [15+ mais scripts existentes]
│
├── 📦 docs/BUDS2 License Registrator/ [BINÁRIOS]
│   ├── seed_key.dll                  ← USE ISTO!
│   ├── BUDS2 License Registrator.exe
│   └── vcinet2.dll
│
├── 🔓 temp_decompiled/BUDS2 License Registrator/ [CÓDIGO]
│   ├── buds2.cs                      ← PROTOCOLO LICENÇA!
│   ├── Devices/BRP.cs                ← IXXAT API!
│   └── [15+ support files]
│
└── 🎮 main.py [INTEGRAÇÃO]
    └── IXXAT support já implementado ✅
```

---

## 📖 Guia de Leitura Recomendado

### Para Iniciant (15 min)
```
1. BUDS2_Executive_Summary.md ← COMECE AQUI
2. BUDS2_Quick_Start_Today.md
3. Execute: bruteforce_seedkey_aggressive.py
```

### Para Técnico (30 min)
```
1. BUDS2_Technical_ReverseEngineering_Plan.md
2. BUDS2_ReversEngineering_Analysis.md
3. Revisar código em temp_decompiled/
```

### Para Implementação (60 min)
```
1. BUDS2_Technical_ReverseEngineering_Plan.md (Phase Details)
2. Analisar buds2_seedkey_results.json (dados reais)
3. Modificar scripts python-code/
4. Integração com main.py
```

### Para Debugging (30 min)
```
1. BUDS2_Quick_Start_Today.md (Troubleshooting)
2. Alterar path em bruteforce_seedkey_aggressive.py
3. Usar dnSpy em tools/ para debugar DLL
```

---

## 🎯 Arquivos por Propósito

### Se você quer... Leia:

| Objetivo | Documento | Tempo |
|----------|-----------|-------|
| Visão geral rápida | Executive Summary | 5 min |
| Começar em 2 horas | Quick Start Today | 10 min |
| Entender arquitetura | Technical Plan | 20 min |
| Análise estrutural | ReversEngineering Analysis | 25 min |
| Executar testes | bruteforce_seedkey_aggressive.py | 5 min running |
| Debugar problemas | Quick Start (Troubleshooting section) | 10 min |
| Integrar com main.py | Technical Plan (Phase 5) | 30 min |
| Mapear componentes | BUDS2_inventory.json | 5 min |

---

## 🔑 Arquivos-Chave Descobertos

### Código-Fonte Descompilado
```
Location: firmware-esp32-projetocan/temp_decompiled/BUDS2 License Registrator/

buds2.cs (150+ linhas)
├── Protocolo TCP mapeado
├── String de conexão: brptuning.com:9005
├── Formato de pacote: CSV (hash,serial,email,...)
└── Resposta: 1 byte (0=sucesso)

Devices/BRP.cs (200+ linhas)
├── Ixxat.Vci3 CAN interface
├── Socket/Channel initialization
├── Message reader/writer
└── Compatible com seu main.py!
```

### DLL para Testar
```
Location: firmware-esp32-projetocan/docs/BUDS2 License Registrator/

seed_key.dll (20 KB)
├── Função: sk_calculate_key()
├── Entrada: (level, seed_buffer, seed_len, key_buffer, max_len, actual_len)
├── Versão byte encontrada: 0xC1
└── Pronto para brute-force!
```

### Scripts Python
```
Location: python-code/

bruteforce_seedkey_aggressive.py (NEW!)
├── Testa todos os cluster types
├── Export em JSON
├── Análise de padrões
└── Ready to run: python bruteforce_seedkey_aggressive.py --full

fake_license_server.py (70% done)
├── Mock TCP server
├── Serve ficções license
└── Próximo: completar 30%
```

---

## 🚀 Quick Commands

### Para Começar AGORA
```powershell
cd c:\Users\johan\Documents\projetoCAN
.\.venv\Scripts\Activate.ps1
python python-code\bruteforce_seedkey_aggressive.py --level 1 --range 0:256
```

### Para Análise Completa
```powershell
python python-code\bruteforce_seedkey_aggressive.py --full
```

### Para Ver Resultados
```powershell
type buds2_seedkey_results.json
```

### Para Debugar DLL
```powershell
# Abrir em dnSpy:
# firmware-esp32-projetocan/tools/dnSpy/dnSpy.exe 
# Load: docs/BUDS2\ License\ Registrator/seed_key.dll
```

---

## 📊 Mapa de Dependências

```
┌─ Executive Summary (visão geral)
│  └─ Quick Start (como começar, 2h)
│  └─ Technical Plan (detalhes, 5 fases)
│
├─ bruteforce_seedkey_aggressive.py
│  ├── Precisa: seed_key.dll ✅ (localizado)
│  ├── Output: buds2_seedkey_results.json
│  └─ Próximo: Análise de padrões
│
├─ fake_license_server.py
│  ├── Precisa: protocolo do buds2.cs ✅ (decompilado)
│  └─ Próximo: Integrar com BUDS2.exe
│
├─ main.py (seu código)
│  ├── ✅ IXXAT support pronto
│  └─ Próximo: Seed/key integration
│
└─ Análise Estrutural (ReversEngineering_Analysis.md)
   ├── JARs location
   ├── DLL dependency tree
   └─ Quick wins
```

---

## 💡 Dicas de Navegação

### Estou Aqui, Não Sei Por Onde Começar
```
→ Leia: BUDS2_Executive_Summary.md (5 min)
→ Siga: 5 passos em BUDS2_Quick_Start_Today.md
```

### Já Executei, Mas Não Funciona
```
→ Seção "Troubleshooting" em BUDS2_Quick_Start_Today.md
→ Alterar path em bruteforce_seedkey_aggressive.py
```

### Tenho Resultados, Agora O Que?
```
→ Analisar buds2_seedkey_results.json
→ Ler: "Próximas Ações" em Executive Summary
→ Próximo: Technical Plan Phase 2
```

### Preciso Integrar ao Main.py
```
→ Technical Plan > Phase 5: Integration
→ Código referência em temp_decompiled/Devices/BRP.cs
```

### Quer Crackear a Licença
```
→ Technical Plan > Phase 1: Mock License Server
→ Referência: temp_decompiled/buds2.cs
→ Script: python-code/fake_license_server.py
```

---

## 🔗 Links Cruzados

| Doc A | Referencia | Doc B | Linha |
|-------|-----------|-------|-------|
| Executive Summary | "Comece AQUI" | Quick Start | Top |
| Quick Start | "Troubleshooting" | section | Lines 234-287 |
| Quick Start | "Próximas Ações" | Technical Plan | All phases |
| Technical Plan | "Código Decompilado" | buds2.cs | Lines 1-100 |
| Technical Plan | "DLL Assinatura" | analyze_seed_key.py | Lines 10-30 |
| ReversEngineering | "Seed/Key Priority" | test_seedkey_dll.py | Full |
| ReversEngineering | "DMS Files" | Demo files/ | .buds2 |

---

## 📈 Progresso Tracking

### Análise Completada ✅
```
✓ Mapeamento estrutural completo
✓ Protocolo de licença decompilado
✓ Seed/Key DLL localizado
✓ Dependências mapeadas
✓ Scripts de teste preparados
✓ Documentação técnica gerada
```

### Pronto para Testar 🟡
```
→ Executar bruteforce_seedkey_aggressive.py
→ Coletar buds2_seedkey_results.json
→ Analisar padrões
```

### Próximas Fases (5h cada)
```
1. Mock License Server [3h]
2. Reverter Seed/Key Algorithm [5h]
3. Crack License Validation [4h]
4. Offline Mode [2h]
5. Main.py Integration [5h]
```

---

## 🎓 Aprendizado

Mientras você faz a engenharia reversa, você aprende sobre:

1. **CAN Protocol** - Como BRP comunica com ECUs
2. **UDS/KWP Diagnostics** - Padrão de diagnóstico automotivo
3. **Seed/Key Algorithms** - Criptografia embarcada
4. **Reverse Engineering** - Análise de binários
5. **Python ctypes** - Interação com DLLs nativas
6. **IXXAT Driver** - Interface CAN profissional
7. **License Systems** - Proteção de software

---

## 📞 Próximas Ações

### HOJE (2 horas)
- [ ] Ler Executive Summary
- [ ] Executar bruteforce_seedkey_aggressive.py
- [ ] Gerar buds2_seedkey_results.json

### ESTA SEMANA (5 horas)
- [ ] Completar análise de padrões
- [ ] Testar/completar mock server
- [ ] Documentar achados

### PRÓXIMAS SEMANAS (15 horas)
- [ ] Implementar gerador seed/key Python
- [ ] Integrar com main.py
- [ ] Teste end-to-end com veículo real

---

## 📋 Checklist de Leitura

- [ ] Executive Summary (5 min)
- [ ] Quick Start Today (10 min)
- [ ] Technical Plan (20 min)
- [ ] ReversEngineering Analysis (25 min)
- [ ] Revisar código decompilado (10 min)
- [ ] Executar script de brute-force (5 min)

**Total: 75 minutos**

---

## 🎬 Comece Aqui

1. **Leia (5 min):** `BUDS2_Executive_Summary.md`
2. **Siga (10 min):** `BUDS2_Quick_Start_Today.md` (5 passos)
3. **Execute (5 min):** `bruteforce_seedkey_aggressive.py`
4. **Analise (10 min):** `buds2_seedkey_results.json`
5. **Próximas ações:** Volte à documentação técnica

---

*Índice de Navegação - 09/03/2026*  
*Atualização: Daily*  
*Última revisão: Hoje ✅*
