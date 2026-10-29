MCU ?= atmega162
F_CPU ?= 16000000UL
PROGRAMMER ?= arduino
PORT ?= COM5
BAUD ?= 19200

CC = avr-gcc
OBJCOPY = avr-objcopy
OBJDUMP = avr-objdump
SIZE = avr-size
AVRDUDE = avrdude

CFLAGS = -mmcu=$(MCU) -DF_CPU=$(F_CPU) -Os -std=gnu11 -Wall -Wextra -Werror -Iinclude
LDFLAGS = -mmcu=$(MCU)

SRC = src/main.c src/usb_fifo.c src/usb_packet.c src/kline.c src/can_sja1000.c
OBJ = $(SRC:.c=.o)
TARGET = build/firmware_avr
ELF = $(TARGET).elf
HEX = $(TARGET).hex
LST = $(TARGET).lst

.PHONY: all clean flash size disasm

all: $(HEX) size

build:
	cmd /c if not exist build mkdir build

$(ELF): build $(OBJ)
	$(CC) $(LDFLAGS) -o $@ $(OBJ)

$(HEX): $(ELF)
	$(OBJCOPY) -O ihex -R .eeprom $(ELF) $(HEX)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

size: $(ELF)
	$(SIZE) $(ELF)

disasm: $(ELF)
	$(OBJDUMP) -S $(ELF) > $(LST)

flash: $(HEX)
	$(AVRDUDE) -p m162 -c $(PROGRAMMER) -P $(PORT) -b $(BAUD) -U flash:w:$(HEX):i

# Lê fuses atuais (seguro, apenas leitura)
read-fuses:
	$(AVRDUDE) -p m162 -c $(PROGRAMMER) -P $(PORT) -b $(BAUD) \
	    -U lfuse:r:-:h -U hfuse:r:-:h -U efuse:r:-:h

# Verifica assinatura do MCU (seguro, não grava nada)
check-sig:
	$(AVRDUDE) -v -p m162 -c $(PROGRAMMER) -P $(PORT) -b $(BAUD) -n

# Dump completo da flash
read-flash:
	$(AVRDUDE) -p m162 -c $(PROGRAMMER) -P $(PORT) -b $(BAUD) \
	    -U flash:r:build/flash_dump.hex:i

clean:
	cmd /c if exist build rmdir /s /q build
	cmd /c if exist src\main.o del /q src\main.o
	cmd /c if exist src\usb_fifo.o del /q src\usb_fifo.o
	cmd /c if exist src\usb_packet.o del /q src\usb_packet.o
	cmd /c if exist src\kline.o del /q src\kline.o
	cmd /c if exist src\can_sja1000.o del /q src\can_sja1000.o