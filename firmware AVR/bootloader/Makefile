# Makefile — Bootloader FT245 para ATmega162
#
# Boot section: 512 palavras (1 KB) → endereço de início byte = 0x3C00
# BOOTSZ1:0 = 10 (hfuse bits 3:2) → 512W
# BOOTRST   = 0  (hfuse bit 0)    → vetor de reset aponta para boot section
#
# Fuses recomendados (verificar com avrdude antes de gravar):
#   lfuse = 0xFF  (cristal externo 16MHz, CKSEL=1111, SUT=11)
#   hfuse = 0xD8  (BOOTSZ=10→512W, BOOTRST=0, JTAGEN=1, SPIEN=0, WDTON=1, EESAVE=0)
#   efuse = 0xFF  (padrão ATmega162)
#
# Para calcular: http://www.engbedded.com/fusecalc/
#
# Gravar bootloader (ICSP — primeira vez):
#   make flash-boot PROGRAMMER=arduino PORT=COM5 BAUD=19200
#
# Configurar fuses (ICSP — uma vez apenas):
#   make fuses PROGRAMMER=arduino PORT=COM5 BAUD=19200
#
# Build apenas:
#   make

MCU       ?= atmega162
F_CPU     ?= 16000000UL
PROGRAMMER ?= arduino
PORT      ?= COM5
BAUD      ?= 19200

# Endereço de início da boot section (bytes) para BOOTSZ=1024W (2KB)
BOOT_START_ADDR = 0x3800

CC      = avr-gcc
OBJCOPY = avr-objcopy
SIZE    = avr-size
AVRDUDE = avrdude

CFLAGS = -mmcu=$(MCU) \
         -DF_CPU=$(F_CPU) \
         -DBOARD_HAS_STATUS_LED=0 \
         -Os \
         -std=gnu11 \
         -Wall -Wextra -Werror \
         -Iinclude \
         -fno-jump-tables \
         -fdata-sections \
         -ffunction-sections

# IMPORTANTE: seção .text começa no endereço da boot section
LDFLAGS = -mmcu=$(MCU) \
           -Wl,-section-start=.text=$(BOOT_START_ADDR) \
           -Wl,--gc-sections \
           -Wl,--relax

SRC    = src/boot_main.c
TARGET = build/bootloader
ELF    = $(TARGET).elf
HEX    = $(TARGET).hex

# Fuses ATmega162:
#   lfuse 0xFF = cristal externo 16MHz, CKDIV8=1, CKOUT=1, SUT=11, CKSEL=1111
#   hfuse 0xD0 = OCDEN=1,JTAGEN=1,SPIEN=0,WDTON=1,EESAVE=0,BOOTSZ=00(2KB),BOOTRST=0
#   efuse 0xFF = padrão (M161C=1)
LFUSE ?= 0xFF
HFUSE ?= 0xD0
EFUSE ?= 0xFF

.PHONY: all clean flash-boot fuses size check-size

all: $(HEX) check-size

build:
	cmd /c if not exist build mkdir build

$(ELF): build $(SRC)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $(SRC)

$(HEX): $(ELF)
	$(OBJCOPY) -O ihex -R .eeprom $(ELF) $(HEX)

size: $(ELF)
	$(SIZE) $(ELF)

# Verifica se o bootloader cabe na boot section (512W = 1024 bytes)
check-size: $(ELF)
	$(SIZE) $(ELF)
	@powershell -Command " \
	  $$text = (& avr-size '$<' | Select-Object -Skip 1 | ForEach-Object { $$_.Trim() -split '\s+' })[0]; \
	  if ([int]$$text -gt 2048) { Write-Host 'ERRO: bootloader muito grande' -ForegroundColor Red; exit 1 } \
	  else { Write-Host ('OK: bootloader ' + $$text + ' / 2048 bytes') -ForegroundColor Green }"

# Grava apenas o bootloader via ICSP (não toca na aplicação)
flash-boot: $(HEX)
	$(AVRDUDE) -p m162 -c $(PROGRAMMER) -P $(PORT) -b $(BAUD) \
	    -U flash:w:$(HEX):i

# Configura fuses — ATENÇÃO: operação irreversível em alguns bits!
# Revise LFUSE/HFUSE antes de executar.
fuses:
	@echo "Gravando fuses: lfuse=$(LFUSE) hfuse=$(HFUSE) efuse=$(EFUSE)"
	@echo "ATENCAO: verifique os valores antes de continuar."
	$(AVRDUDE) -p m162 -c $(PROGRAMMER) -P $(PORT) -b $(BAUD) \
	    -U lfuse:w:$(LFUSE):m \
	    -U hfuse:w:$(HFUSE):m \
	    -U efuse:w:$(EFUSE):m

# Lê fuses atuais (seguro, só leitura)
read-fuses:
	$(AVRDUDE) -p m162 -c $(PROGRAMMER) -P $(PORT) -b $(BAUD) \
	    -U lfuse:r:-:h -U hfuse:r:-:h -U efuse:r:-:h

# Lê dump completo da flash
read-flash:
	$(AVRDUDE) -p m162 -c $(PROGRAMMER) -P $(PORT) -b $(BAUD) \
	    -U flash:r:build/flash_dump.hex:i
	@echo "Flash dump salvo em build/flash_dump.hex"

clean:
	cmd /c if exist build rmdir /s /q build
