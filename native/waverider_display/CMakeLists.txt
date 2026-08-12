add_executable(waverider_display main.c)
target_link_libraries(waverider_display freewili2_bsp onewili_fwgui)
fw2_display_app(waverider_display
    NAME "WaveRider"
    POWER_ZONES DISPLAY RGB_LEDS USB_HUB
    VERSION 001
    DESCRIPTION "WaveRider RTL-SDR foxhunt display with direct hardware buttons"
    REPOSITORY "https://github.com/3DDEio/freewili-waverider")
