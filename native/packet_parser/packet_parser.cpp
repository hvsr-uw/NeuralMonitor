#include <cstdint>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr uint8_t kVersion = 1;

uint16_t read_u16(const std::vector<uint8_t>& data, size_t offset) {
  return static_cast<uint16_t>((data[offset] << 8) | data[offset + 1]);
}

uint32_t read_u32(const std::vector<uint8_t>& data, size_t offset) {
  return (static_cast<uint32_t>(data[offset]) << 24) |
         (static_cast<uint32_t>(data[offset + 1]) << 16) |
         (static_cast<uint32_t>(data[offset + 2]) << 8) |
         static_cast<uint32_t>(data[offset + 3]);
}

uint64_t read_u64(const std::vector<uint8_t>& data, size_t offset) {
  uint64_t value = 0;
  for (size_t i = 0; i < 8; ++i) {
    value = (value << 8) | data[offset + i];
  }
  return value;
}

uint32_t crc32(const std::vector<uint8_t>& data, size_t length) {
  uint32_t crc = 0xFFFFFFFF;
  for (size_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (int bit = 0; bit < 8; ++bit) {
      const uint32_t mask = -(crc & 1u);
      crc = (crc >> 1) ^ (0xEDB88320u & mask);
    }
  }
  return ~crc;
}

std::vector<uint8_t> hex_to_bytes(const std::string& hex) {
  if (hex.size() % 2 != 0) {
    throw std::runtime_error("hex input length must be even");
  }
  std::vector<uint8_t> bytes;
  bytes.reserve(hex.size() / 2);
  for (size_t i = 0; i < hex.size(); i += 2) {
    bytes.push_back(static_cast<uint8_t>(std::stoul(hex.substr(i, 2), nullptr, 16)));
  }
  return bytes;
}
}  // namespace

int main(int argc, char** argv) {
  if (argc != 2) {
    std::cerr << "usage: packet_parser <frame-hex>\n";
    return 2;
  }

  try {
    const auto frame = hex_to_bytes(argv[1]);
    constexpr size_t header_size = 19;
    if (frame.size() < header_size + 4) {
      throw std::runtime_error("frame_too_short");
    }
    if (frame[0] != 'N' || frame[1] != 'M') {
      throw std::runtime_error("bad_magic");
    }
    if (frame[2] != kVersion) {
      throw std::runtime_error("unsupported_version");
    }

    const uint16_t payload_size = read_u16(frame, 3);
    const uint32_t sequence = read_u32(frame, 5);
    const uint64_t timestamp_us = read_u64(frame, 9);
    const uint16_t channels = read_u16(frame, 17);
    const size_t expected_size = header_size + payload_size + 4;
    if (frame.size() != expected_size) {
      throw std::runtime_error("bad_length");
    }

    const uint32_t expected_crc = read_u32(frame, frame.size() - 4);
    const uint32_t actual_crc = crc32(frame, frame.size() - 4);
    std::cout << "{"
              << "\"sequence_number\":" << sequence << ","
              << "\"device_timestamp_us\":" << timestamp_us << ","
              << "\"channel_count\":" << channels << ","
              << "\"payload_size\":" << payload_size << ","
              << "\"checksum_valid\":" << (expected_crc == actual_crc ? "true" : "false")
              << "}\n";
    return 0;
  } catch (const std::exception& exc) {
    std::cerr << exc.what() << "\n";
    return 1;
  }
}

