#ifndef PROTOCOL_V2_H
#define PROTOCOL_V2_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define UDP_PORT 8080
#define PROTOCOL_MAGIC 0x49474F52 // "IGOR" in ASCII

// Ground truth dimensions for Project IGOR neural network
#define IGOR_OBS_DIM 74     // 64 LiDAR + 6 IMU + 3 Twist + 1 Heading
#define IGOR_ACTION_DIM 3   // delta_vx, delta_vy, delta_omega

// Status codes
#define STATUS_OK                0x00000000
#define STATUS_ERR_MAGIC         0x00000001
#define STATUS_ERR_CRC           0x00000002
#define STATUS_ERR_DIM           0x00000003
#define STATUS_PL_TIMEOUT        0x00000004
#define STATUS_SAFETY_INTERVENE  0x00000005

#pragma pack(push, 1)

/**
 * SensorPacketV2: Jetson Orin Nano -> DE10-Nano FPGA HPS
 * Transmits the exact 74-D observation vector both as floats and Q8.8 fixed-point integers.
 */
typedef struct {
    uint32_t magic;              // Must be PROTOCOL_MAGIC (0x49474F52)
    uint32_t frame_id;           // Monotonically increasing frame sequence
    uint64_t timestamp_ns;       // Host monotonic timestamp in nanoseconds
    float linear_velocity[3];    // Commanded Vx, Vy, Vz
    float angular_velocity[3];   // Commanded Wx, Wy, Wz
    uint32_t sensor_data_len;    // Fixed to 74
    float sensor_data[IGOR_OBS_DIM];    // 74 float inputs
    int16_t q8_8_data[IGOR_OBS_DIM];    // 74 Q8.8 quantized inputs (int16)
    uint32_t crc32;              // CRC32 checksum over the packet excluding this field
} SensorPacketV2;

/**
 * InferenceResponsePacketV2: DE10-Nano FPGA HPS -> Jetson Orin Nano
 * Transmits 3 delta actions in float and Q8.8 format along with execution metrics.
 */
typedef struct {
    uint32_t magic;              // Must be PROTOCOL_MAGIC (0x49474F52)
    uint32_t frame_id;           // Echoed frame sequence from request
    uint64_t timestamp_ns;       // Echoed timestamp for RTT calculation
    uint32_t status_code;        // Status / Error flags
    uint32_t num_outputs;        // Fixed to 3
    float ai_results[IGOR_ACTION_DIM];    // Delta actions [dvx, dvy, dwz] in [-1.0, 1.0]
    int16_t q8_8_results[IGOR_ACTION_DIM];// Raw Q8.8 actions from FPGA
    uint32_t execution_cycles;   // Accelerator hardware clock cycles
    uint32_t crc32;              // CRC32 checksum over the packet excluding this field
} InferenceResponsePacketV2;

#pragma pack(pop)

// Standard CRC-32 (IEEE 802.3 polynomial: 0xEDB88320)
static inline uint32_t crc32_bitwise(const uint8_t *data, size_t length) {
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < length; ++i) {
        crc ^= data[i];
        for (int j = 0; j < 8; ++j) {
            crc = (crc >> 1) ^ (0xEDB88320 & (-(int)(crc & 1)));
        }
    }
    return ~crc;
}

static inline void serialize_sensor_packet(SensorPacketV2 *pkt) {
    pkt->magic = PROTOCOL_MAGIC;
    pkt->sensor_data_len = IGOR_OBS_DIM;
    pkt->crc32 = crc32_bitwise((const uint8_t *)pkt, offsetof(SensorPacketV2, crc32));
}

static inline int validate_sensor_packet(const SensorPacketV2 *pkt) {
    if (pkt->magic != PROTOCOL_MAGIC) return -1;
    if (pkt->sensor_data_len != IGOR_OBS_DIM) return -2;
    uint32_t expected_crc = crc32_bitwise((const uint8_t *)pkt, offsetof(SensorPacketV2, crc32));
    if (pkt->crc32 != expected_crc) return -3;
    return 0;
}

static inline void serialize_response_packet(InferenceResponsePacketV2 *pkt) {
    pkt->magic = PROTOCOL_MAGIC;
    pkt->num_outputs = IGOR_ACTION_DIM;
    pkt->crc32 = crc32_bitwise((const uint8_t *)pkt, offsetof(InferenceResponsePacketV2, crc32));
}

static inline int validate_response_packet(const InferenceResponsePacketV2 *pkt) {
    if (pkt->magic != PROTOCOL_MAGIC) return -1;
    if (pkt->num_outputs != IGOR_ACTION_DIM) return -2;
    uint32_t expected_crc = crc32_bitwise((const uint8_t *)pkt, offsetof(InferenceResponsePacketV2, crc32));
    if (pkt->crc32 != expected_crc) return -3;
    return 0;
}

#ifdef __cplusplus
}
#endif

#endif // PROTOCOL_V2_H
