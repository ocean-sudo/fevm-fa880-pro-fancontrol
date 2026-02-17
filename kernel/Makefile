# Makefile for FEVM FA880 PRO Fan Control WMI driver
# Build from this directory: kernel/

KVER ?= $(shell uname -r)
KDIR ?= /lib/modules/$(KVER)/build
PWD  := $(shell pwd)

obj-m := fevm_ip3_wmi_fan.o

all:
	$(MAKE) LLVM=1 -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean

load:
	sudo insmod fevm_ip3_wmi_fan.ko

unload:
	sudo rmmod fevm_ip3_wmi_fan

reload: unload load

info:
	modinfo fevm_ip3_wmi_fan.ko

.PHONY: all clean load unload reload info
