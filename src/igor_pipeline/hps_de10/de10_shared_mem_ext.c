#include "de10_shared_mem_ext.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>
#include <time.h>

int hal_init(SoC_HAL_Context *ctx, int is_mock) {
    if (!ctx) return -1;
    memset(ctx, 0, sizeof(SoC_HAL_Context));
    ctx->is_mock = is_mock;

    if (is_mock) {
        // Allocate virtual mock memory
        ctx->lw_base_virt = calloc(1, 0x1000);
        ctx->shared_ram_virt = calloc(1, SHARED_RAM_SPAN);
        if (!ctx->lw_base_virt || !ctx->shared_ram_virt) {
            hal_cleanup(ctx);
            return -2;
        }
        ctx->shared_ram_phys = SHARED_RAM_BASE;
    } else {
        ctx->mem_fd = open("/dev/mem", O_RDWR | O_SYNC);
        if (ctx->mem_fd < 0) {
            perror("[HAL] Failed to open /dev/mem");
            return -3;
        }

        ctx->lw_base_virt = mmap(NULL, LWHPS2FPGA_SPAN, PROT_READ | PROT_WRITE,
                                 MAP_SHARED, ctx->mem_fd, LWHPS2FPGA_BASE);
        if (ctx->lw_base_virt == MAP_FAILED) {
            perror("[HAL] Failed to mmap LWHPS2FPGA");
            close(ctx->mem_fd);
            return -4;
        }

        ctx->shared_ram_virt = mmap(NULL, SHARED_RAM_SPAN, PROT_READ | PROT_WRITE,
                                    MAP_SHARED, ctx->mem_fd, SHARED_RAM_BASE);
        if (ctx->shared_ram_virt == MAP_FAILED) {
            perror("[HAL] Failed to mmap SHARED_RAM");
            munmap(ctx->lw_base_virt, LWHPS2FPGA_SPAN);
            close(ctx->mem_fd);
            return -5;
        }
        ctx->shared_ram_phys = SHARED_RAM_BASE;
    }

    volatile uint32_t *accel = (volatile uint32_t *)((uint8_t *)ctx->lw_base_virt + AI_ACCEL_OFFSET);
    ctx->accel_ctrl    = &accel[REG_CONTROL];
    ctx->accel_in_ptr  = &accel[REG_IN_PTR];
    ctx->accel_out_ptr = &accel[REG_OUT_PTR];
    ctx->accel_len     = &accel[REG_LENGTH];
    ctx->accel_status  = &accel[REG_STATUS];
    ctx->accel_cycles  = &accel[REG_CYCLES];

    // Configure Ping-Pong buffers (4MB chunks)
    uint8_t *base = (uint8_t *)ctx->shared_ram_virt;
    ctx->in_buf_ping  = (int16_t *)(base + 0x000000);
    ctx->out_buf_ping = (int16_t *)(base + 0x400000);
    ctx->in_buf_pong  = (int16_t *)(base + 0x800000);
    ctx->out_buf_pong = (int16_t *)(base + 0xC00000);

    ctx->in_phys_ping  = ctx->shared_ram_phys + 0x000000;
    ctx->out_phys_ping = ctx->shared_ram_phys + 0x400000;
    ctx->in_phys_pong  = ctx->shared_ram_phys + 0x800000;
    ctx->out_phys_pong = ctx->shared_ram_phys + 0xC00000;

    return 0;
}

void hal_write_reg(SoC_HAL_Context *ctx, uint32_t reg_idx, uint32_t val) {
    if (!ctx || !ctx->lw_base_virt) return;
    volatile uint32_t *accel = (volatile uint32_t *)((uint8_t *)ctx->lw_base_virt + AI_ACCEL_OFFSET);
    accel[reg_idx] = val;
}

uint32_t hal_read_reg(SoC_HAL_Context *ctx, uint32_t reg_idx) {
    if (!ctx || !ctx->lw_base_virt) return 0;
    volatile uint32_t *accel = (volatile uint32_t *)((uint8_t *)ctx->lw_base_virt + AI_ACCEL_OFFSET);
    return accel[reg_idx];
}

int hal_trigger_inference(SoC_HAL_Context *ctx, int bank, uint32_t num_inputs, uint32_t timeout_us) {
    if (!ctx) return -1;

    uint32_t in_phys  = (bank == 0) ? ctx->in_phys_ping : ctx->in_phys_pong;
    uint32_t out_phys = (bank == 0) ? ctx->out_phys_ping : ctx->out_phys_pong;

    *ctx->accel_in_ptr  = in_phys;
    *ctx->accel_out_ptr = out_phys;
    *ctx->accel_len     = num_inputs;
    *ctx->accel_ctrl    = 0x01; // Start pulse

    if (ctx->is_mock) {
        // Mock software execution: simple sleep and synthetic done
        usleep(50);
        *ctx->accel_status = 0x01; // Done asserted
        *ctx->accel_ctrl = 0x00;
        return 0;
    }

    // Hardware polling with watchdog deadline
    uint32_t waited_us = 0;
    while ((*ctx->accel_status & 0x01) == 0) {
        usleep(10);
        waited_us += 10;
        if (waited_us >= timeout_us) {
            // Soft-reset pulse to unhang PL
            *ctx->accel_ctrl = 0x02;
            usleep(10);
            *ctx->accel_ctrl = 0x00;
            return -1; // Timeout
        }
    }

    *ctx->accel_ctrl = 0x00;
    return 0;
}

void hal_cleanup(SoC_HAL_Context *ctx) {
    if (!ctx) return;
    if (ctx->is_mock) {
        if (ctx->lw_base_virt) free(ctx->lw_base_virt);
        if (ctx->shared_ram_virt) free(ctx->shared_ram_virt);
    } else {
        if (ctx->lw_base_virt && ctx->lw_base_virt != MAP_FAILED) {
            munmap(ctx->lw_base_virt, LWHPS2FPGA_SPAN);
        }
        if (ctx->shared_ram_virt && ctx->shared_ram_virt != MAP_FAILED) {
            munmap(ctx->shared_ram_virt, SHARED_RAM_SPAN);
        }
        if (ctx->mem_fd >= 0) {
            close(ctx->mem_fd);
        }
    }
    memset(ctx, 0, sizeof(SoC_HAL_Context));
}
