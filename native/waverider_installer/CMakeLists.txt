set(WAVERIDER_UF2
    "${CMAKE_BINARY_DIR}/apps/waverider_display/waverider_display.uf2")
set(WAVERIDER_PAYLOAD_C
    "${CMAKE_CURRENT_BINARY_DIR}/waverider_payload.c")

add_custom_command(
    OUTPUT "${WAVERIDER_PAYLOAD_C}"
    COMMAND "${Python3_EXECUTABLE}"
            "${CMAKE_CURRENT_LIST_DIR}/../embed_binary.py"
            --xor 0xa5
            "${WAVERIDER_UF2}"
            "${WAVERIDER_PAYLOAD_C}"
            waverider_payload
    DEPENDS waverider_display "${WAVERIDER_UF2}"
            "${CMAKE_CURRENT_LIST_DIR}/../embed_binary.py"
    VERBATIM)

add_executable(waverider_installer main.c "${WAVERIDER_PAYLOAD_C}")
target_link_libraries(waverider_installer freewili2_bsp onewili_fwgui)
fw2_display_app(waverider_installer
    NAME "WaveRider Installer"
    POWER_ZONES DISPLAY SDCARD
    VERSION 001
    DESCRIPTION "Install the verified WaveRider app onto the Main SD card"
    REPOSITORY "https://github.com/3DDEio/freewili-waverider")
