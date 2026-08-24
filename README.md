# hat-tool

**Chainbus HAT Management Tool** - A CLI/TUI utility for registering, generating, and managing Hardware Attached on Top (HAT) boards for the Chainbus ecosystem.

## Overview

`hat-tool` streamlines the development workflow for Chainbus HAT boards by providing:

- **Interactive Registration Wizard** - Register new HAT boards with validated type IDs, slugs, and metadata
- **EEPROM Binary Generation** - Produce 32-byte binary payloads for HAT EEPROM identification
- **Devicetree Overlay Generator** - Create Zephyr devicetree overlays (`.overlay`) for peripheral chips
- **Chip Catalog Management** - Extensible library of peripheral chip DTS templates (I2C, SPI, root devices)

## Installation

```bash
# From the project root
pip install -e scripts/hat-tool
```

The tool installs as the `hat` command.

## Quick Start

```bash
# Register a new HAT (interactive TUI)
hat register

# Generate a devicetree overlay for a registered HAT
hat generate

# Remove a HAT from the registry
hat remove
```

## Project Structure

```
hat-tool/
├── pyproject.toml          # Package configuration
├── registry.yaml           # HAT registry (vendor_id + hat entries)
├── hat_tool/
│   ├── cli.py              # CLI entry point
│   ├── core.py             # Core logic: registry, binary, DTS generation
│   ├── tui.py              # Interactive terminal UI (questionary + rich)
│   └── chip_lib/
│   │   ├── chip_lib.py     # Chip catalog management
│   │   ├── ds3231.dts      # DS3231 RTC DTS template
│   │   ├── pca9555.dts     # PCA9555 GPIO expander DTS template
│   │   └── bmi270.dts      # BMI270 IMU DTS template
```

## Registry Format (`registry.yaml`)

```yaml
vendor_id: 4292 # 0x10C4 (Konar vendor ID)
hats:
  - type_id: 256 # 0x0100 - Unique 16-bit type ID
    slug: mms_hat_rtc_sd # Board identifier (max 20 ASCII chars)
    description: "A board with 4 SD card slots and an DS3231 RTC module."
    hw_rev: 1 # Hardware revision (uint32)
    sw_ver: 100 # Minimum software version (uint32)
```

### Type ID Ranges

| Range               | Category                     |
| ------------------- | ---------------------------- |
| `0x0100` - `0x01FF` | Digital / Relays / GPIO      |
| `0x0200` - `0x02FF` | Analog / Sensors             |
| `0x0300` - `0x03FF` | Communications / CAN / RS485 |

The tool automatically suggests the next free ID in the selected category.

## EEPROM Binary Format

The generated `.bin` file (32 bytes) contains:

| Offset | Size     | Field                             |
| ------ | -------- | --------------------------------- |
| 0x00   | 2 bytes  | Vendor ID (little-endian)         |
| 0x02   | 2 bytes  | Type ID (little-endian)           |
| 0x04   | 20 bytes | Slug (ASCII, null-padded)         |
| 0x18   | 4 bytes  | Hardware Revision (little-endian) |
| 0x1C   | 4 bytes  | Software Version (little-endian)  |

```python
# struct format: "<HH20sII"
struct.pack("<HH20sII", vendor_id, type_id, slug_bytes, hw_rev, sw_ver)
```

## Devicetree Overlay Generation

The `generate` command creates a `.overlay` file compatible with Zephyr's devicetree:

```dts
/* Auto-generated overlay for mms_hat_rtc_sd */
hat_mms_hat_rtc_sd: hat@0 {
    compatible = "konar,mms-hat";
    reg = <0>;
    type-id = <0x0100>;
    label = "mms_hat_rtc_sd";

    /* Slot 0 Virtual I2C Bus Bridge */
    slot0_i2c: i2c-bridge {
        compatible = "konar,mms-hat-i2c-bridge";
        i2c-bus = <&chainbus_i2c>;
        #address-cells = <1>;
        #size-cells = <0>;

        ds3231: ds3231@68 {
            compatible = "maxim,ds3231-mfd";
            reg = <0x68>;
            status = "okay";
            rtc0: ds3231_rtc {
                compatible = "maxim,ds3231-rtc";
                isw-gpios = placeholder;
                status = "okay";
            };
        };

        expander0: gpio@20 {
            compatible = "nxp,pca9555";
            reg = <0x20>;
            gpio-controller;
            #gpio-cells = <2>;
            ngpios = <16>;
            status = "okay";
        };
    };

    /* Slot 0 Virtual SPI Bus Bridge */
    slot0_spi: spi-bridge {
        compatible = "konar,mms-hat-spi-bridge";
        spi-bus = <&chainbus_spi>;
        #address-cells = <1>;
        #size-cells = <0>;
        /* No SPI devices attached */
    };
};
```

## Chip Catalog

Built-in chips in `hat_tool/chip_lib/`:

| Key       | Bus | Address | Description                             |
| --------- | --- | ------- | --------------------------------------- |
| `ds3231`  | I2C | 0x68    | DS3231 Real-Time Clock with MFD support |
| `pca9555` | I2C | 0x20    | PCA9555 16-bit I2C GPIO Expander        |
| `bmi270`  | SPI | 0x68    | BMI270 IMU (accelerometer/gyroscope)    |

### Adding Custom Chips

Use the interactive wizard (`hat register` → Peripheral Chip Selection → Add Custom Chip) or programmatically:

```python
from hat_tool.chip_lib import add_chip_to_catalog

add_chip_to_catalog(
    key="mcp23017",
    bus="i2c",
    dts_content='''
mcp23017: gpio@20 {
    compatible = "microchip,mcp23017";
    reg = <0x20>;
    gpio-controller;
    #gpio-cells = <2>;
    ngpios = <16>;
    status = "okay";
};
''',
    description="MCP23017 16-bit I2C GPIO Expander",
    address="0x20"
)
```

DTS templates support `{slot}` placeholder for slot-aware node names.

## Commands

### `west hat register`

Interactive wizard to:

1. Select hardware category (determines type ID range)
2. Assign/validate Type ID (16-bit hex, must be unique)
3. Enter board slug (unique, alphanumeric + underscore, ≤20 chars)
4. Provide description
5. Set hardware revision & software version
6. Select peripheral chips from catalog (I2C, SPI, root)
7. Review summary and commit

Outputs:

- Updated `registry.yaml`
- EEPROM binary: `<slug>.bin` in current directory

### `west hat generate`

Interactive wizard to:

1. Select registered HAT
2. Choose Chainbus slot index (0-7)
3. Select peripheral chips for this overlay
4. Specify output file path

Output:

- Devicetree overlay: `<slug>.overlay` (or custom path)

### `west hat remove`

Interactive wizard to:

1. List registered HATs
2. Select HAT to remove
3. Double-confirmation for safety
4. Remove from `registry.yaml`

## Dependencies

- **Python** ≥ 3.10
- **pyyaml** ≥ 6.0 - YAML parsing
- **west** ≥ 1.0.0 - Zephyr meta-tool integration
- **questionary** ≥ 2.0.0 - Interactive prompts
- **rich** ≥ 13.0.0 - Terminal formatting

## License

Apache-2.0 - See individual files for SPDX headers.

## Related

- [Zephyr RTOS](https://zephyrproject.org/)
- [West](https://docs.zephyrproject.org/latest/develop/west/)
- Chainbus HAT Specification (internal)
