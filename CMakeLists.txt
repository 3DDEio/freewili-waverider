cmake_minimum_required(VERSION 3.21)

# FreeWili 2 uses the RP2350B (48 GPIO) board definition supplied by the
# pinned WiliBSP submodule. Do not add the WiliBSP repository root: external
# apps consume only the board-support library and the explicitly required
# OneWili transport library.
set(PICO_BOARD freewili2 CACHE STRING "Board type")
list(APPEND PICO_BOARD_HEADER_DIRS
     "${CMAKE_CURRENT_LIST_DIR}/wilibsp/bsp/boards")
set(PICO_PIO_USB_PATH
    "${CMAKE_CURRENT_LIST_DIR}/wilibsp/bsp/third_party/Pico-PIO-USB")
include("${CMAKE_CURRENT_LIST_DIR}/wilibsp/pico_sdk_import.cmake")

project(waverider C CXX ASM)
set(CMAKE_C_STANDARD 11)
find_package(Python3 COMPONENTS Interpreter REQUIRED)
# Build dates make otherwise identical UF2 files change every day. Release
# identity comes from the app metadata VERSION and published SHA-256 digest;
# omit the SDK's optional compile-date record so a pinned-source rebuild is
# reproducible and can be compared byte-for-byte with the release artifact.
add_compile_definitions(PICO_NO_BI_PROGRAM_BUILD_DATE=1)
pico_sdk_init()

add_subdirectory(wilibsp/bsp)
add_subdirectory(wilibsp/libs/onewili)
add_subdirectory(native/waverider_display
                 "${CMAKE_BINARY_DIR}/apps/waverider_display")
add_subdirectory(native/waverider_installer
                 "${CMAKE_BINARY_DIR}/apps/waverider_installer")
