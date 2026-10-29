# 🚀 BUDS2 Reverse Engineering - Guia Rápido "Comece Hoje"

## Status Atual

✅ **Você já tem 70% do trabalho feito!**

```
✓ main.py com IXXAT funcionando
✓ Código decompilado do License Registrator  
✓ Protocolo TCP de licença mapeado
✓ Scripts Python para seed/key análise
✓ DLL para testar (em docs/BUDS2 License Registrator/)
✓ Demo files para teste (.buds2)
✓ Código documentado e testável
```

---

## 5 Passos para começar HOJE (2 horas)

### PASSO 1: Localizar & Verificar seed_key.dll (10 min)

```bash
# Verificar se DLL está acessível
ls -la firmware-esp32-projetocan/docs/"BUDS2 License Registrator"/

# Deve retornar:
# -rwx------ seed_key.dll
# -rwx------ BUDS2 License Registrator.exe
# -rwx------ vcinet2.dll
```

**Resultado esperado:** Arquivos visíveis e acessíveis

---

### PASSO 2: Executar Script de Brute Force (15 min)

```bash
# Ir para pasta raiz do projeto
cd c:\Users\johan\Documents\projetoCAN

# Ativar venv
.\.venv\Scripts\Activate.ps1

# Rodar brute force SIMPLES (apenas 1 nível)
python python-code\bruteforce_seedkey_aggressive.py --level 1 --range 0:256

# OU rodar COMPLETO (todos 20 níveis, pode demorar 10-15 min)
python python-code\bruteforce_seedkey_aggressive.py --full
```

**O que observar:**
```
[!] FOUND: Level=X ClusterType=0x## KeyLen=## Key=...

Se vir isso = SUCESSO! Algoritmo funcional.
Se não vir nada = DLL diferente ou estrutura errada.
```

---

### PASSO 3: Analisar Resultados (15 min)

```bash
# Script exportou em: buds2_seedkey_results.json

# Abrir e verificar:
cat buds2_seedkey_results.json | python -m json.tool

# Procurar por:
# - Quantos "sucessos" temos? (success_count)
# - Quantos níveis tiveram resultado? (level_X)
# - Keys são diferentes ou todas iguais?
# - Padrão identificável?
```

**Arquivo esperado:**
```json
{
  "metadata": {
    "success_count": 5,
    "results": {
      "level_1": [
        {"cluster_type": 0x00, "key": "3f4a..."},
        {"cluster_type": 0x01, "key": "4b5c..."}
      ]
    }
  }
}
```

---

### PASSO 4: Mock License Server (20 min)

```bash
# Script já existe e está 70% pronto:
cat python-code/fake_license_server.py

# Necessário completar:
# 1. Bind em localhost:9005 ✓ (provavelmente já tem)
# 2. Aguardar magic string "BUDS2 License Client..." ✓
# 3. Responder com 0x00 (sucesso) ← VERIFICAR
# 4. Servir licença fake ← COMPLETAR

# Teste rápido:
python python-code/fake_license_server.py

# Em outra aba terminal:
netstat -an | findstr 9005

# Deve mostrar: LISTENING 0.0.0.0:9005
```

---

### PASSO 5: Documentar & Próximas Ações (20 min)

```bash
# Criar arquivo com achados
touch firmware-esp32-projetocan/docs/BUDS2_Session_LOG_$(date +%Y%m%d).md

# Adicionar:
# - Quais cluster types funcionaram?
# - Quais níveis tiveram sucesso?
# - Padrão identificado?
# - Próximas ações
```

---

## 🎯 Árvore de Decisão - O Que Fazer Depois

```
┌─ Executou bruteforce_seedkey_aggressive.py?
│
├─ ✅ SIM, achei resultados!
│   ├─ Keys são todas iguais?
│   │   └─ ✅ Sim → Possível hardcoding ou cache
│   │       └─ Ir para: FASE 2 (análise de algoritmo)
│   │   └─ ❌ Não → Cada cluster type gera key diferente
│   │       └─ Ir para: FASE 3 (reverter algoritmo)
│   │
│   └─ Encontrou em múltiplos níveis?
│       └─ ✅ Sim (0-19) → Algoritmo parece genérico
│       └─ ❌ Não (apenas níveis específicos) → Segurança por nível
│
└─ ❌ NÃO, nenhum resultado
    ├─ Erro de DLL loading?
    │   └─ Ir para: DEBUG DLL PATH
    ├─ Erro de assinatura função?
    │   └─ Ir para: INVESTIGATE SK2-SK12.dll
    └─ Estrutura seed incorreta?
        └─ Ir para: TEST ALTERNATE STRUCTURES
```

---

## 🔧 Se Não Funcionar - Troubleshooting Rápido

### Erro: "DLL não encontrado"
```bash
# Verificar caminhos alternativos:
find . -name "seed_key.dll" 2>/dev/null

# Ou expandir busca:
find c:\Users\johan -name "seed_key.dll" 2>/dev/null
```

### Erro: "OSError 126 - Module not found"
```bash
# DLL tem dependências. Verificar com:
dumpbin /IMPORTS firmware-esp32-projetocan/docs/"BUDS2 License Registrator"/seed_key.dll

# Copiar DLLs dependentes para mesma pasta:
# vcinet2.dll (Ixxat)
# Outras conforme necessário
```

### Erro: "Return code != 0"
```bash
# DLL retornou erro. Significa:
# - Nível inválido? (testar 0-19)
# - Seed structure errada? (testar alternativas)
# - DLL esperava dados diferentes?

# Solução: Usar dnSpy para debugar
# Abrir:  firmware-esp32-projetocan/tools/dnSpy/
# Load:   seed_key.dll
```

### Nenhuma resposta - DLL não retorna
```bash
# Possibilidade: DLL trava (infinite loop?)
# Solução: Usar timeout
# (modificar bruteforce_seedkey_aggressive.py)

# Ou usar API Monitor para ver o que DLL faz internamente
# Procure por: CreateFile, GetComputerName, Registry reads
```

---

## 📊 Checklist de Progresso

Use isto para acompanhar sua evolução:

**ITERATION 1 - DLL Testing (Este fim de semana)**
- [ ] Confirmado DLL acessível
- [ ] Brute force executado (pelo menos 1 level)
- [ ] Resultados exportados em JSON
- [ ] 0 sucessos OU múltiplos sucessos relatados

**ITERATION 2 - Análise & Padrões (Próxima semana)**
- [ ] Identificado padrão nas keys
- [ ] Documentado resultado esperado vs. real
- [ ] Decidido próximo passo (algoritmo reverso vs. DLL direto)
- [ ] Fake server testado manualmente

**ITERATION 3 - Integração (2 semanas)**
- [ ] Seed/key generator em Python puro
- [ ] License validation bypassada
- [ ] BUDS2 funciona offline
- [ ] Main.py integrado com BUDS2 functions

---

## 💡 Dicas Práticas

### 1. **Registre outputs intermediários**
```bash
# Redirecionar output para arquivo:
python bruteforce_seedkey_aggressive.py --full > buds2_run_20260309.log 2>&1

# Depois analisar:
grep "\[!\] FOUND" buds2_run_20260309.log
```

### 2. **Use git para controle de versão**
```bash
cd firmware-esp32-projetocan
git add docs/BUDS2_*.md
git add docs/BUDS2_Analysis/
git commit -m "BUDS2 reverse engineering checkpoint"
```

### 3. **Paralelizar testes**
```bash
# Testar versão SK2-SK12 DLL em paralelo:
# Terminal 1: SK_Dll
python bruteforce_seedkey_aggressive.py --dll lib/SK_Dll.dll

# Terminal 2: SK11_Dll  
python bruteforce_seedkey_aggressive.py --dll lib/SK11_Dll.dll
```

### 4. **Documentar achados em tempo real**
```bash
# Ter um arquivo de notas aberto:
# firmware-esp32-projetocan/docs/BUDS2_Session_NotesLive.md

# Adicionar findings conforme descobrir:
# - 12:34 - Level 1 funciona, cluster type 0x00-0x10
# - 12:45 - Padrão: key muda por cluster type
# - 13:00 - Algoritmo aparenta ser: XOR(seed, magic_value)
```

---

## 🎁 Arquivo de Saída Esperado

Ao final destas 5 etapas, você terá:

```
firmware-esp32-projetocan/
├── docs/
│   ├── BUDS2_ReversEngineering_Analysis.md (✓ criado)
│   ├── BUDS2_Technical_ReverseEngineering_Plan.md (✓ criado)
│   ├── BUDS2_Analysis/
│   │   └── buds2_inventory.json (✓ criado)
│   └── BUDS2_Session_LOG_20260309.md (← você cria)
│
├── python-code/
│   ├── bruteforce_seedkey_aggressive.py (✓ novo)
│   ├── buds2_seedkey_results.json (← gerado ao rodar)
│   └── [scripts existentes melhorados]
│
└── [IXXAT integration ready]
```

---

## 📞 Próximas Conversas

Quando tiver completado os 5 passos, traga:

1. **Output do brute force:** `buds2_seedkey_results.json`
2. **Log de execução:** terminal output ou arquivo .log
3. **Observações:** o que funcionou, o que não funcionou
4. **Decisão:** próximo passo (reverter algoritmo ou usar DLL directly)

---

## Comece AGORA!

```bash
# Copie e cole:
cd c:\Users\johan\Documents\projetoCAN
.\.venv\Scripts\Activate.ps1
python python-code\bruteforce_seedkey_aggressive.py --level 1 --range 0:256
```

**Tempo estimado:** 2-5 minutos  
**Resultado esperado:** `buds2_seedkey_results.json` com findings

---

*Guia prático - 09/03/2026*  
*Próximo checkpoint: Reports de teste*
