import board
import busio
import time
import displayio
import terminalio
from adafruit_display_text import label
import adafruit_displayio_ssd1306
import adafruit_gps

# —— DISPLAY SETUP ——  
WIDTH, HEIGHT, BORDER = 128, 64, 2

i2c = board.STEMMA_I2C()
displayio.release_displays()
display_bus = displayio.I2CDisplay(i2c, device_address=0x3D)
display = adafruit_displayio_ssd1306.SSD1306(display_bus, width=WIDTH, height=HEIGHT)

root = displayio.Group()
display.root_group = root

# White border
bmp = displayio.Bitmap(WIDTH, HEIGHT, 1)
pal = displayio.Palette(1)
pal[0] = 0xFFFFFF
root.append(displayio.TileGrid(bmp, pixel_shader=pal, x=0, y=0))

# Black interior
bmp2 = displayio.Bitmap(WIDTH - 2*BORDER, HEIGHT - 2*BORDER, 1)
pal2 = displayio.Palette(1)
pal2[0] = 0x000000
root.append(displayio.TileGrid(bmp2, pixel_shader=pal2, x=BORDER, y=BORDER))

# Labels
dt_label  = label.Label(terminalio.FONT, text="--/--/---- --:--:--", color=0xFFFFFF, x=8,  y=15)
lat_label = label.Label(terminalio.FONT, text="Lat: --.------",         color=0xFFFFFF, x=8,  y=27)
lon_label = label.Label(terminalio.FONT, text="Lon: --.------",         color=0xFFFFFF, x=8,  y=39)
alt_label = label.Label(terminalio.FONT, text="Alt: ----.- m",          color=0xFFFFFF, x=8,  y=51)
root.append(dt_label)
root.append(lat_label)
root.append(lon_label)
root.append(alt_label)

# —— GPS SETUP ——  
gps = adafruit_gps.GPS_GtopI2C(i2c, address=0x10, debug=False)
gps.send_command(b"PMTK314,0,1,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0")  # RMC + GGA
gps.send_command(b"PMTK220,1000")  # 1 Hz update
gps.debug = True

# —— HELPERS ——  
def days_in_month(m, y):
    if m in (1,3,5,7,8,10,12): return 31
    if m == 2:
        return 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28
    return 30

# Zeller’s congruence for Gregorian calendar → weekday 0=Mon…6=Sun
def weekday(y, m, d):
    Y, M = (y, m)
    if M < 3:
        Y -= 1
        M += 12
    K = Y % 100
    J = Y // 100
    h = (d + (13*(M+1))//5 + K + K//4 + J//4 + 5*J) % 7  # 0=Sat,1=Sun,…6=Fri
    return (h + 5) % 7  # convert: 0=Mon…6=Sun

# Find second Sunday in March and first Sunday in November, then create UTC thresholds
def dst_utc_bounds(year):
    # Second Sunday in March
    w1 = weekday(year, 3, 1)
    first_sun_mar = 1 + ((6 - w1) % 7)
    second_sun_mar = first_sun_mar + 7
    # DST starts at 2:00 local (EST) = 07:00 UTC
    start = (year, 3, second_sun_mar, 7, 0, 0)
    # First Sunday in November
    w2 = weekday(year, 11, 1)
    first_sun_nov = 1 + ((6 - w2) % 7)
    # DST ends at 2:00 local (EDT) = 06:00 UTC
    end   = (year, 11, first_sun_nov, 6, 0, 0)
    return start, end

# Convert a UTC tuple + offset (in hours) into local date/time, rolling as needed
def utc_to_local(y, mo, d, h, mi, s, offset):
    h2 = h + offset
    d2, mo2, y2 = d, mo, y
    if h2 < 0:
        h2 += 24
        d2 -= 1
        if d2 < 1:
            mo2 -= 1
            if mo2 < 1:
                mo2 = 12
                y2 -= 1
            d2 = days_in_month(mo2, y2)
    elif h2 >= 24:
        h2 -= 24
        d2 += 1
        if d2 > days_in_month(mo2, y2):
            d2 = 1
            mo2 += 1
            if mo2 > 12:
                mo2 = 1
                y2 += 1
    return y2, mo2, d2, h2, mi, s

# —— MAIN LOOP ——  
while True:
    gps.update()
    ts = gps.timestamp_utc  # struct_time-like 9‑tuple
    if gps.has_fix and ts:
        # Extract just the first six fields
        y, mo, d, h, mi, s = ts[0:6]

        # Compute DST bounds for this year
        start, end = dst_utc_bounds(y)

        # Decide offset: EDT (−4) if in [start, end), else EST (−5)
        offset = -4 if (start <= (y,mo,d,h,mi,s) < end) else -5

        # Apply offset to get local time
        y2, mo2, d2, h2, mi2, s2 = utc_to_local(y, mo, d, h, mi, s, offset)

        # Safe formatting of position
        lat_label.text = f"Lat: {gps.latitude:.6f}" if gps.latitude is not None else "Lat: --.------"
        lon_label.text = f"Lon: {gps.longitude:.6f}" if gps.longitude is not None else "Lon: --.------"
        alt_label.text = f"Alt: {gps.altitude_m:.1f} m" if gps.altitude_m is not None else "Alt: ----.- m"
        # Display MM/DD/YYYY HH:MM:SS
        dt_label.text  = f"{mo2:02d}/{d2:02d}/{y2:04d} {h2:02d}:{mi2:02d}:{s2:02d}"
    else:
        # Waiting for fix
        lat_label.text = "Lat: --.------"
        lon_label.text = "Lon: --.------"
        alt_label.text = "Alt: ----.- m"
        dt_label.text  = "--/--/---- --:--:--"

    time.sleep(1)
