CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -pthread -I../protocol
TARGET = de10_server_daemon

SRCS = de10_server_daemon.c de10_shared_mem_ext.c
OBJS = $(SRCS:.c=.o)

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CC) $(CFLAGS) -o $@ $^

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJS) $(TARGET)

.PHONY: all clean
