# SPDX-License-Identifier: Apache-2.0

"""
Chip Catalog for Chainbus HAT Management Tool.

This module manages the catalog of supported peripheral chips.
Each chip entry contains:
- bus: "i2c", "spi", or "root" (for non-bus devices like LEDs)
- dts_file: path to the .dts template file in chip_lib/
- dts: the loaded DTS content (with {slot} placeholder for slot-aware devices)
"""

from pathlib import Path

# Chip library directory
CHIP_LIB_DIR = Path(__file__).parent / "chip_lib"


def load_dts_file(filename: str) -> str:
    """Load a DTS template file from chip_lib/"""
    file_path = CHIP_LIB_DIR / filename
    if file_path.exists():
        return file_path.read_text()
    return ""


# Built-in chip catalog - loaded from chip_lib/ directory
CHIP_CATALOG = {
    "ds3231": {
        "bus": "i2c",
        "dts_file": "ds3231.dts",
        "dts": load_dts_file("ds3231.dts"),
        "description": "DS3231 Real-Time Clock with MFD support",
        "address": "0x68",
    },
    "pca9555": {
        "bus": "i2c",
        "dts_file": "pca9555.dts",
        "dts": load_dts_file("pca9555.dts"),
        "description": "PCA9555 16-bit I2C GPIO Expander",
        "address": "0x20",
    },
}


def get_chip_catalog() -> dict:
    """Get the current chip catalog."""
    return CHIP_CATALOG


def add_chip_to_catalog(
    key: str,
    bus: str,
    dts_content: str,
    description: str,
    address: str = "N/A",
    dts_filename: str = None,
) -> bool:
    """
    Add a new chip to the catalog and save its DTS template to chip_lib/.
    
    Args:
        key: Unique identifier for the chip (e.g., "mcp23017")
        bus: Bus type - "i2c", "spi", or "root"
        dts_content: DTS template content with {slot} placeholder if needed
        description: Human-readable description
        address: I2C/SPI address or "N/A"
        dts_filename: Optional custom filename (defaults to {key}.dts)
    
    Returns:
        True if added successfully, False if key already exists
    """
    if key in CHIP_CATALOG:
        return False
    
    if dts_filename is None:
        dts_filename = f"{key}.dts"
    
    # Save DTS file to chip_lib/
    file_path = CHIP_LIB_DIR / dts_filename
    file_path.write_text(dts_content)
    
    # Add to catalog
    CHIP_CATALOG[key] = {
        "bus": bus,
        "dts_file": dts_filename,
        "dts": dts_content,
        "description": description,
        "address": address,
    }
    return True


def remove_chip_from_catalog(key: str) -> bool:
    """Remove a chip from the catalog (does not delete the .dts file)."""
    if key in CHIP_CATALOG:
        del CHIP_CATALOG[key]
        return True
    return False


def list_chips_by_bus(bus_type: str) -> list:
    """List chip keys filtered by bus type."""
    return [k for k, v in CHIP_CATALOG.items() if v["bus"] == bus_type]


def get_chip_dts(key: str, slot: int = 0) -> str:
    """Get formatted DTS content for a chip at a specific slot."""
    if key not in CHIP_CATALOG:
        return ""
    dts = CHIP_CATALOG[key]["dts"]
    # Only replace {slot} placeholder if present, to avoid issues with literal braces
    if "{slot}" in dts:
        return dts.replace("{slot}", str(slot))
    return dts
