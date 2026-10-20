#pragma once
// Simulator stand-in for ESP-IDF esp_random() (the simulator library has none).
#include <cstdint>
#include <random>
inline uint32_t esp_random() {
  static std::mt19937 gen{std::random_device{}()};
  return static_cast<uint32_t>(gen());
}
