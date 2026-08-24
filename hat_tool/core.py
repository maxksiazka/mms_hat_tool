# SPDX-License-Identifier: Apache-2.0

import struct
from pathlib import Path

import yaml
from hat_tool.chip_lib import CHIP_CATALOG


class Registry:
    def __init__(self, data=None):
        self.vendor_id = data.get("vendor_id", 0x10C4) if data else 0x10C4
        self.hats = data.get("hats", []) if data else []

    def get_entries(self):
        return self.hats

    def get_next_free_id(self, base_id: int) -> int:
        used_ids = {h["type_id"] for h in self.hats}
        candidate = base_id
        while candidate in used_ids:
            candidate += 1
        return candidate

    def validate_type_id(self, val: str):
        try:
            if not val.startswith("0x"):
                return "Must start with '0x' prefix"
            num = int(val, 16)
            if not (0x0001 <= num <= 0xFFFF):
                return "Must be 16-bit hex (0x0001 - 0xFFFF)"
            if any(h["type_id"] == num for h in self.hats):
                return f"ID {val} is already allocated in registry.yaml!"
            return True
        except ValueError:
            return "Invalid hexadecimal value"

    def validate_slug(self, val: str):
        if not val or len(val) > 20:
            return "Slug must be between 1 and 20 characters"
        if not val.isascii():
            return "Slug must contain ASCII characters only"
        if any(not (c.isalnum() or c in "_") for c in val):
            return "Slug can only contain alphanumeric characters and underscores"
        if any(h["slug"] == val for h in self.hats):
            return f"Slug '{val}' already exists in registry.yaml!"
        return True

    def add_entry(
        self, type_id: int, slug: str, description: str, hw_rev: int, sw_ver: int
    ):
        self.hats.append(
            {
                "type_id": type_id,
                "slug": slug,
                "description": description,
                "hw_rev": hw_rev,
                "sw_ver": sw_ver,
            }
        )
        self.hats.sort(key=lambda x: x["type_id"])

    def remove_entry(self, type_id: int) -> bool:
        initial_len = len(self.hats)
        self.hats = [h for h in self.hats if h["type_id"] != type_id]
        return len(self.hats) < initial_len


def load_registry(yaml_path: Path) -> Registry:
    if not yaml_path.exists():
        return Registry()
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f) or {}
    return Registry(data)


def save_registry(yaml_path: Path, registry: Registry):
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    with open(yaml_path, "w") as f:
        yaml.dump(
            {"vendor_id": registry.vendor_id, "hats": registry.hats},
            f,
            sort_keys=False,
        )


def generate_binary_payload(
    registry: Registry, type_id: int, out_dir: Path = None
) -> Path:
    target = next((h for h in registry.get_entries() if h["type_id"] == type_id), None)
    if not target:
        raise ValueError(f"Type ID 0x{type_id:04X} not found in registry.")

    dest = out_dir or Path.cwd()
    bin_path = dest / f"{target['slug']}.bin"

    slug_bytes = target["slug"].encode("ascii").ljust(20, b"\x00")
    # Layout: vendor_id(2B) + type_id(2B) + slug(20B) + hw_rev(4B) + sw_ver(4B) = 32 Bytes
    payload = struct.pack(
        "<HH20sII",
        registry.vendor_id,
        target["type_id"],
        slug_bytes,
        target["hw_rev"],
        target["sw_ver"],
    )

    bin_path.write_bytes(payload)
    return bin_path


def remove_registry_entry(registry: Registry, type_id: int) -> bool:
    """Remove a HAT entry from the registry by type_id."""
    return registry.remove_entry(type_id)


def generate_dts_overlay(
    slug: str,
    type_id_str: str,
    out_path: Path,
    slot: int = 0,
    selected_chips: list[str] = None,
) -> Path:
    from hat_tool.chip_lib import get_chip_dts, CHIP_CATALOG
    
    out_path.parent.mkdir(parents=True, exist_ok=True)
    node_name = slug.replace("-", "_")

    # Default composition matching the reference static RTC/SD HAT if unassigned
    selected_chips = (
        selected_chips
        if selected_chips is not None
        else ["ds3231", "pca9555", "gpio_leds_expander0"]
    )

    i2c_nodes, spi_nodes, root_nodes = [], [], []

    for key in selected_chips:
        if key not in CHIP_CATALOG:
            continue
        entry = CHIP_CATALOG[key]
        formatted_dts = get_chip_dts(key, slot)

        if entry["bus"] == "i2c":
            i2c_nodes.append(formatted_dts)
        elif entry["bus"] == "spi":
            spi_nodes.append(formatted_dts)
        elif entry["bus"] == "root":
            root_nodes.append(formatted_dts)

    def _indent(text: str, spaces: int) -> str:
        pad = " " * spaces
        return "\n".join(
            f"{pad}{line}" if line.strip() else "" for line in text.splitlines()
        )

    i2c_body = (
        "\n\n".join(_indent(n, 16) for n in i2c_nodes)
        if i2c_nodes
        else "                /* No I2C devices attached */"
    )
    spi_body = (
        "\n\n".join(_indent(n, 16) for n in spi_nodes)
        if spi_nodes
        else "                /* No SPI devices attached */"
    )
    root_body = (
        "\n\n".join(_indent(n, 12) for n in root_nodes) if root_nodes else ""
    )

    dts_content = f"""/* Auto-generated overlay for {slug} */
hat_{node_name}: hat@{slot} {{
    compatible = "konar,mms-hat"; /*[cite: 1] */
    reg = <{slot}>; /*[cite: 1] */
    type-id = <{type_id_str}>;
    label = "{slug}";

    /* Slot {slot} Virtual I2C Bus Bridge */
    slot{slot}_i2c: i2c-bridge {{
        compatible = "konar,mms-hat-i2c-bridge"; /*[cite: 1] */
        i2c-bus = <&chainbus_i2c>; /*[cite: 1] */
        #address-cells = <1>; /*[cite: 1] */
        #size-cells = <0>; /*[cite: 1] */

{i2c_body}
    }};

    /* Slot {slot} Virtual SPI Bus Bridge */
    slot{slot}_spi: spi-bridge {{
        compatible = "konar,mms-hat-spi-bridge"; /*[cite: 1] */
        spi-bus = <&chainbus_spi>; /*[cite: 1] */
        #address-cells = <1>; /*[cite: 1] */
        #size-cells = <0>; /*[cite: 1] */

{spi_body}
    }};
{f"{root_body}" if root_body else ""}
}};
"""
    out_path.write_text(dts_content)
    return out_path
