#include "protocol_v2.h"
#include "de10_shared_mem_ext.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <time.h>

static volatile int g_running = 1;

void sig_handler(int sig) {
    (void)sig;
    g_running = 0;
}

static inline uint64_t get_time_ns() {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

int main(int argc, char **argv) {
    int is_mock = 0;
    int port = UDP_PORT;

    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--mock") == 0) {
            is_mock = 1;
        } else if (strcmp(argv[i], "--hw") == 0) {
            is_mock = 0;
        } else if (strcmp(argv[i], "--port") == 0 && i + 1 < argc) {
            port = atoi(argv[++i]);
        }
    }

    printf("==================================================================\n");
    printf("  DE10-Nano HPS Dual-Mode AI Acceleration Daemon (Project IGOR)\n");
    printf("  Mode: %s | Port: %d | Obs Dim: %d | Action Dim: %d\n",
           is_mock ? "MOCK (Virtual Memory)" : "HARDWARE (/dev/mem PL Bridges)",
           port, IGOR_OBS_DIM, IGOR_ACTION_DIM);
    printf("==================================================================\n");

    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);

    SoC_HAL_Context soc;
    if (hal_init(&soc, is_mock) != 0) {
        fprintf(stderr, "[ERROR] Failed to initialize SoC HAL in %s mode\n", is_mock ? "mock" : "hardware");
        return 1;
    }

    int sockfd = socket(AF_INET, SOCK_DGRAM, 0);
    if (sockfd < 0) {
        perror("[ERROR] Failed to open UDP socket");
        hal_cleanup(&soc);
        return 2;
    }

    int opt = 1;
    setsockopt(sockfd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in server_addr, client_addr;
    socklen_t client_len = sizeof(client_addr);
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(port);
    server_addr.sin_addr.s_addr = INADDR_ANY;

    if (bind(sockfd, (struct sockaddr *)&server_addr, sizeof(server_addr)) < 0) {
        perror("[ERROR] Failed to bind UDP port");
        close(sockfd);
        hal_cleanup(&soc);
        return 3;
    }

    printf("[DE10] Daemon listening on UDP port %d...\n", port);

    SensorPacketV2 rx_pkt;
    InferenceResponsePacketV2 tx_pkt;
    int current_bank = 0;
    uint32_t processed_frames = 0;

    while (g_running) {
        ssize_t n = recvfrom(sockfd, &rx_pkt, sizeof(SensorPacketV2), 0,
                             (struct sockaddr *)&client_addr, &client_len);
        if (n <= 0) continue;

        if (validate_sensor_packet(&rx_pkt) != 0) {
            fprintf(stderr, "[WARN] Received invalid packet (magic/len/crc mismatch)!\n");
            continue;
        }

        // 1. Double buffering: Select ping or pong buffer
        int16_t *in_buf  = (current_bank == 0) ? soc.in_buf_ping  : soc.in_buf_pong;
        int16_t *out_buf = (current_bank == 0) ? soc.out_buf_ping : soc.out_buf_pong;

        // 2. Transfer pre-quantized Q8.8 data to DDR buffer
        memcpy(in_buf, rx_pkt.q8_8_data, IGOR_OBS_DIM * sizeof(int16_t));

        // 3. Trigger FPGA hardware or mock inference
        int trig_res = hal_trigger_inference(&soc, current_bank, IGOR_OBS_DIM, 20000); // 20ms timeout

        // Prepare response
        tx_pkt.magic = PROTOCOL_MAGIC;
        tx_pkt.frame_id = rx_pkt.frame_id;
        tx_pkt.timestamp_ns = rx_pkt.timestamp_ns; // Echo for RTT
        tx_pkt.num_outputs = IGOR_ACTION_DIM;

        if (trig_res == 0) {
            tx_pkt.status_code = STATUS_OK;
            if (is_mock) {
                // Software emulation of reactive policy
                float min_lidar = 1.0f;
                for (int i = 0; i < 64; ++i) {
                    if (rx_pkt.sensor_data[i] < min_lidar) min_lidar = rx_pkt.sensor_data[i];
                }
                if (min_lidar < 0.35f) {
                    tx_pkt.ai_results[0] = -0.9f;
                    tx_pkt.ai_results[1] = 0.0f;
                    tx_pkt.ai_results[2] = 0.0f;
                } else if (min_lidar < 0.60f) {
                    tx_pkt.ai_results[0] = -0.4f;
                    tx_pkt.ai_results[1] = 0.0f;
                    tx_pkt.ai_results[2] = 0.0f;
                } else {
                    tx_pkt.ai_results[0] = 0.0f;
                    tx_pkt.ai_results[1] = 0.0f;
                    tx_pkt.ai_results[2] = 0.0f;
                }
                tx_pkt.q8_8_results[0] = (int16_t)(tx_pkt.ai_results[0] * 256.0f);
                tx_pkt.q8_8_results[1] = (int16_t)(tx_pkt.ai_results[1] * 256.0f);
                tx_pkt.q8_8_results[2] = (int16_t)(tx_pkt.ai_results[2] * 256.0f);
                tx_pkt.execution_cycles = 1200;
            } else {
                // Read actions from DDR output buffer
                for (int i = 0; i < IGOR_ACTION_DIM; ++i) {
                    tx_pkt.q8_8_results[i] = out_buf[i];
                    tx_pkt.ai_results[i] = (float)out_buf[i] / 256.0f;
                }
                tx_pkt.execution_cycles = hal_read_reg(&soc, REG_CYCLES);
            }
        } else {
            tx_pkt.status_code = STATUS_PL_TIMEOUT;
            memset(tx_pkt.ai_results, 0, sizeof(tx_pkt.ai_results));
            memset(tx_pkt.q8_8_results, 0, sizeof(tx_pkt.q8_8_results));
            tx_pkt.execution_cycles = 0;
        }

        serialize_response_packet(&tx_pkt);
        sendto(sockfd, &tx_pkt, sizeof(InferenceResponsePacketV2), 0,
               (struct sockaddr *)&client_addr, client_len);

        current_bank = 1 - current_bank; // Flip ping-pong bank
        processed_frames++;
    }

    printf("\n[DE10] Server daemon shutting down. Total frames served: %u\n", processed_frames);
    close(sockfd);
    hal_cleanup(&soc);
    return 0;
}
