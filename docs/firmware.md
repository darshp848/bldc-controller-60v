# Firmware notes

MAB's MD80 firmware is closed and built for MAB's hardware, so it will not run on this
board. The firmware has to be written (or ported from an open FOC stack such as the
moteus, ODrive or SimpleFOC code bases) against the pin map below. To keep working with
MAB's CANdle and actuators, it also has to speak MAB's CAN-FD frame and register
protocol, which is documented on the MAB site.

## Pin map (STM32G474CEU6, QFN-48)

| Function | Pin | Peripheral |
|---|---|---|
| INHA / INHB / INHC | PA8 / PA9 / PA10 | TIM1_CH1 / CH2 / CH3 (AF6) |
| INLA / INLB / INLC | PB13 / PB14 / PB15 | TIM1_CH1N / CH2N / CH3N (AF6) |
| SOA / SOB / SOC | PA0 / PA1 / PA2 | ADC12_IN1 / ADC12_IN2 / ADC1_IN3 |
| VBUS_SENSE | PA3 | ADC1_IN4 (100k / 5.1k, 20.6:1) |
| TEMP_FET / TEMP_MOTOR | PB0 / PB1 | ADC1_IN15 / ADC1_IN12 (10k pull-up to 3V3A) |
| DRV8353 SPI | PA5 SCK, PA6 MISO, PA7 MOSI, PA4 nCS | SPI1 (AF5), mode 1, <= 10 MHz |
| DRV_EN / DRV_nFAULT | PC6 / PC10 | GPIO out (100k pull-down) / EXTI in |
| Encoder + AUX1 SPI | PB3 SCK, PB4 MISO, PB5 MOSI | SPI3 (AF6), mode 1 |
| Encoder nCS / AUX1 nCS | PA15 / PB9 | GPIO |
| RS-422 TX / RX | PB10 / PB11 | USART3 (AF7), or TIM for BiSS/SSI clocking |
| AUX GPIO A / B | PB6 / PB7 | GPIO / TIM4_CH1-2 (brake PWM on GPIO B as MD80) |
| CAN RX / TX | PA11 / PA12 | FDCAN1 (AF9) |
| CAN termination | PB12 | GPIO, high = 120 Ohm on |
| LED green / red | PC13 / PC11 | GPIO |
| HSE 8 MHz | PF0 / PF1 | |
| SWD | PA13 / PA14, NRST | Tag-Connect TC2030-NL (SWO not connected; PB3 is SPI3) |
| BOOT0 | PB8 | 10k pull-down; set nSWBOOT0 in option bytes |

Confirm the ADC channel numbers in CubeMX before writing drivers; they were taken from the
G474 alternate-function table, not generated.

## Clocks

HSE 8 MHz -> PLL (M = 2, N = 80) -> VCO 320 MHz; R = 2 gives SYSCLK 160 MHz, Q = 4 gives
FDCAN 80 MHz. 80 MHz divides evenly into 1, 2, 5 and 8 Mbit/s (10 time quanta at 8 Mbit/s),
which 170 MHz would not.

## PWM, sensing, control

- TIM1 centre-aligned, ARR = 2000 at 160 MHz -> 40 kHz. DRV8353 in 6x PWM mode; MCU dead time
  ~150 ns on top of the driver's handshake dead time.
- Sample SOA/SOB/SOC at the counter underflow (all low-side FETs on), ADC1+ADC2 dual simultaneous,
  triggered from TIM1 TRGO2. With 0.5 mOhm shunts and CSA gain 20: 10 mV/A, +/-140 A range,
  ~80 mA per LSB.
- Loop rates to match the MD80: current/torque and impedance 40 kHz, velocity 5 kHz,
  position 1 kHz. CORDIC for sin/cos, FMAC optional.

## DRV8353S SPI configuration (starting values)

| Register field | Value | Reason |
|---|---|---|
| PWM_MODE | 6x | independent HS/LS from TIM1 |
| IDRIVEP_HS/LS | 300 mA | ~50 ns Miller plateau on ISC022N10NM6, tune for ringing |
| IDRIVEN_HS/LS | 600 mA | |
| TDRIVE | 1000 ns | |
| VDS_LVL | 0.45 V | trips at ~130 A hot / ~200 A cold R_DS(on) |
| OCP_MODE | latched fault | report over CAN, clear with ENABLE pulse |
| CSA_GAIN | 20 V/V | see above |
| VREF_DIV | on | output centred at VREF/2 = 1.65 V |
| DEAD_TIME | 100 ns | plus MCU dead time |

## Protection thresholds (60 V design)

| Condition | Threshold | Action |
|---|---|---|
| Undervoltage | VBUS < 10.5 V | disable bridge (LM5164 UVLO is ~10.8 V rising) |
| Regen soft limit | VBUS > 56 V | ramp regenerative (negative-power) current limit to zero |
| Overvoltage fault | VBUS > 63 V | disable bridge, flag fault |
| Hardware | TVS conducts from 66.7 V | last resort only; it cannot absorb braking energy |
| MOSFET temperature | 100 C, 20 C hysteresis | same as MD80 |
| Motor temperature | user limit <= 140 C | same as MD80 |
| Phase overcurrent | software limit from config, DRV VDS OCP as backstop | |

There is no brake resistor on the MD80 or on this board. On a battery bus the battery takes
the regen current; on a lab supply that cannot sink current the bus will pump up during hard
deceleration, which is what the 56 V / 63 V thresholds are for.

## Encoder

AS5047P over SPI3 at up to 10 MHz, 14-bit angle (register 0x3FFF, even parity). AUX1 shares
SCK/MOSI/MISO through 33 Ohm series resistors with its own chip select, so external SPI
encoders (MAB ME-am, CubeMars CM) keep working. AUX2 RS-422 serves the RLS AksIM-2 / Orbis.
