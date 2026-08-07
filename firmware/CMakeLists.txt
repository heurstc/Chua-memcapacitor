cmake_minimum_required(VERSION 3.13)

# Point PICO_SDK_PATH at your pico-sdk checkout before running cmake, e.g.:
#   export PICO_SDK_PATH=~/pico-sdk
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(chaos_monitor C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(chaos_monitor
    src/main.c
    src/ads1262.c
    src/sampler.c
    src/usb_descriptors.c
)

target_include_directories(chaos_monitor PRIVATE src)

# tusb_config.h must be on the include path — create it below if it doesn't exist.
target_compile_definitions(chaos_monitor PRIVATE
    PICO_RP2350=1
)

target_link_libraries(chaos_monitor
    pico_stdlib
    pico_multicore
    hardware_spi
    hardware_gpio
    tinyusb_device
    tinyusb_board
)

# Disable USB UART stdio; all output goes through TinyUSB CDC.
pico_enable_stdio_usb(chaos_monitor 0)
pico_enable_stdio_uart(chaos_monitor 1)  # UART0 for debug if needed

pico_add_extra_outputs(chaos_monitor)   # generates .uf2, .hex, .bin
