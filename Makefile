.PHONY: all clean kernel userspace

all: kernel

kernel:
	$(MAKE) -C kernel

clean:
	$(MAKE) -C kernel clean
