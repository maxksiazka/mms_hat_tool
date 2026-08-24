# SPDX-License-Identifier: Apache-2.0

import sys
import os
from pathlib import Path
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from hat_tool.core import (
    load_registry, save_registry, generate_binary_payload, 
    generate_dts_overlay, remove_registry_entry
)
from hat_tool.chip_lib import (
    CHIP_CATALOG, get_chip_catalog, add_chip_to_catalog,
    list_chips_by_bus
)

console = Console()

# Resolve paths relative to scripts/hat-tool/ location
TOOL_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = TOOL_DIR.parents[1]
REGISTRY_FILE = TOOL_DIR / "registry.yaml"
CHIP_LIB_DIR = TOOL_DIR / "chip_lib"


class HatTUI:
    def __init__(self):
        self.registry = load_registry(REGISTRY_FILE)

    def _print_header(self, title: str, style: str = "cyan"):
        console.print(Panel(f"[bold {style}]{title}[/bold {style}]", expand=False))

    def _confirm_action(self, message: str) -> bool:
        return questionary.confirm(message).ask() or False

    # ============================================================
    # REGISTER WIZARD
    # ============================================================
    def register_wizard(self):
        self._print_header("Chainbus HAT Registration Wizard")

        # Category selection
        category = questionary.select(
            "Hardware Category Range:",
            choices=[
                "Digital / Relays / GPIO (0x0100+)",
                "Analog / Sensors (0x0200+)",
                "Communications / CAN / RS485 (0x0300+)",
                "Custom Entry"
            ]
        ).ask()

        if category is None:
            return

        base_id = 0x0100 if "Digital" in category else 0x0200 if "Analog" in category else 0x0300
        suggested_id = self.registry.get_next_free_id(base_id)

        # Type ID input with validation
        type_id_hex = questionary.text(
            "Assigned Type ID (Hex):",
            default=f"0x{suggested_id:04X}",
            validate=lambda val: self.registry.validate_type_id(val)
        ).ask()

        if type_id_hex is None:
            return

        # Slug input with validation
        slug = questionary.text(
            "Board Slug (max 20 ASCII chars, alphanumeric + underscore):",
            validate=lambda val: self.registry.validate_slug(val)
        ).ask()

        if slug is None:
            return

        # Description
        desc = questionary.text("Short Description:").ask()
        if desc is None:
            return

        # Hardware revision (uint32)
        hw_rev_str = questionary.text(
            "Hardware Revision (integer):",
            default="1",
            validate=lambda val: val.isdigit() and 0 <= int(val) <= 0xFFFFFFFF or "Must be a valid uint32 integer"
        ).ask()
        if hw_rev_str is None:
            return
        hw_rev = int(hw_rev_str)

        # Software version (uint32)
        sw_ver_str = questionary.text(
            "Minimum Software Version (integer):",
            default="1",
            validate=lambda val: val.isdigit() and 0 <= int(val) <= 0xFFFFFFFF or "Must be a valid uint32 integer"
        ).ask()
        if sw_ver_str is None:
            return
        sw_ver = int(sw_ver_str)

        type_id = int(type_id_hex, 16)

        # Chip selection
        console.print()
        self._print_header("Peripheral Chip Selection", "yellow")
        selected_chips = self._chip_selection_wizard()
        
        # If user selected chips not in catalog, offer to add them
        # (This is handled within _chip_selection_wizard)

        # Summary Table
        console.print()
        table = Table(title="HAT Registry Entry Summary")
        table.add_column("Field", style="bold yellow")
        table.add_column("Value", style="bold green")
        table.add_row("Type ID", f"0x{type_id:04X}")
        table.add_row("Slug", slug)
        table.add_row("Description", desc)
        table.add_row("HW Rev", str(hw_rev))
        table.add_row("SW Ver", str(sw_ver))
        table.add_row("Peripheral Chips", ", ".join(selected_chips) if selected_chips else "None")
        console.print(table)

        if self._confirm_action("Commit to registry.yaml and generate EEPROM binary?"):
            self.registry.add_entry(type_id, slug, desc, hw_rev, sw_ver)
            save_registry(REGISTRY_FILE, self.registry)
            
            # Generate EEPROM binary in current working directory
            bin_path = generate_binary_payload(self.registry, type_id, out_dir=Path.cwd())
            console.print(f"[bold green]✔ Registry updated: {REGISTRY_FILE}[/bold green]")
            console.print(f"[bold green]✔ EEPROM binary written: {bin_path}[/bold green]")

    def _chip_selection_wizard(self) -> list[str]:
        """Interactive chip selection from catalog with option to add new chips."""
        selected = []
        
        while True:
            action = questionary.select(
                "Peripheral Management:",
                choices=[
                    "Add I2C Device",
                    "Add SPI Device", 
                    "Add Root Device (GPIO, LEDs, etc.)",
                    "View Current Selection",
                    "Done"
                ]
            ).ask()
            
            if action is None or action == "Done":
                break
            
            if action == "View Current Selection":
                if selected:
                    table = Table(title="Selected Peripheral Chips")
                    table.add_column("Key", style="cyan")
                    table.add_column("Bus", style="yellow")
                    table.add_column("Description", style="green")
                    table.add_column("Address", style="magenta")
                    for key in selected:
                        chip = CHIP_CATALOG[key]
                        table.add_row(key, chip["bus"], chip["description"], chip["address"])
                    console.print(table)
                else:
                    console.print("[yellow]No chips selected yet[/yellow]")
                continue
            
            # Determine bus type
            bus_type = "i2c" if "I2C" in action else "spi" if "SPI" in action else "root"
            
            # Show available chips for this bus type
            available = list_chips_by_bus(bus_type)
            
            choices = []
            for key in available:
                chip = CHIP_CATALOG[key]
                choices.append(f"{key} - {chip['description']} ({chip['address']})")
            
            choices.append("➕ Add Custom Chip...")
            
            choice = questionary.select(
                f"Select {bus_type.upper()} device:",
                choices=choices
            ).ask()
            
            if choice is None or choice == "➕ Add Custom Chip...":
                if choice == "➕ Add Custom Chip...":
                    self._add_custom_chip(bus_type)
                continue
            
            # Extract key from choice
            key = choice.split(" - ")[0]
            if key not in selected:
                selected.append(key)
                console.print(f"[green]Added {key}[/green]")
            else:
                console.print(f"[yellow]{key} already selected[/yellow]")
        
        return selected

    def _add_custom_chip(self, bus_type: str):
        """Add a custom chip to the catalog."""
        console.print()
        self._print_header(f"Add Custom {bus_type.upper()} Chip", "magenta")
        
        key = questionary.text(
            "Chip Key (unique identifier, lowercase, no spaces):",
            validate=lambda val: (
                val and val.islower() and val.replace("_", "").isalnum() and val not in CHIP_CATALOG
            ) or "Invalid key: must be lowercase alphanumeric/underscore, unique"
        ).ask()
        
        if key is None:
            return
        
        description = questionary.text("Description:").ask()
        if description is None:
            return
        
        address = questionary.text(
            f"{bus_type.upper()} Address (e.g., 0x48 for I2C, or N/A):",
            default="N/A" if bus_type == "root" else "0x"
        ).ask()
        if address is None:
            return
        
        console.print("[dim]Enter DTS template content. Use {slot} placeholder for slot-aware nodes.[/dim]")
        console.print("[dim]Press Ctrl+D (or Enter on empty line twice) when done.[/dim]")
        
        # Multi-line input for DTS content
        dts_lines = []
        empty_count = 0
        while True:
            try:
                line = questionary.text("").ask()
                if line is None or (line == "" and empty_count > 0):
                    break
                if line == "":
                    empty_count += 1
                else:
                    empty_count = 0
                dts_lines.append(line)
            except (EOFError, KeyboardInterrupt):
                break
        
        if not dts_lines:
            console.print("[yellow]No DTS content provided, cancelling[/yellow]")
            return
        
        dts_content = "\n".join(dts_lines)
        
        # Save to catalog
        if add_chip_to_catalog(key, bus_type, dts_content, description, address):
            console.print(f"[green]✔ Added custom chip '{key}' to catalog[/green]")
        else:
            console.print(f"[red]Failed to add chip (key may already exist)[/red]")

    # ============================================================
    # GENERATE WIZARD (Devicetree Overlay)
    # ============================================================
    def generate_wizard(self):
        self._print_header("Devicetree Overlay Generator", "yellow")

        entries = self.registry.get_entries()
        if not entries:
            console.print("[bold red]Registry is empty. Run 'west hat register' first.[/bold red]")
            return

        # Select HAT
        choices = [f"0x{h['type_id']:04X} : {h['slug']} - {h['description']}" for h in entries]
        selected = questionary.select("Select target HAT:", choices=choices).ask()
        
        if selected is None:
            return
        
        # Parse selection
        parts = selected.split(" : ")
        type_id_str = parts[0]
        slug_str = parts[1].split(" - ")[0]
        type_id = int(type_id_str, 16)

        # Select Chainbus Slot (0-7)
        slot = questionary.select(
            "Target Chainbus Slot Index:",
            choices=[str(i) for i in range(8)],
            default="0"
        ).ask()
        
        if slot is None:
            return
        slot = int(slot)

        # Chip selection for overlay
        console.print()
        self._print_header("Peripheral Chip Selection for Overlay", "yellow")
        console.print("[dim]Select which peripheral chips to include in this overlay[/dim]")
        selected_chips = self._chip_selection_for_overlay()
        
        # Output path
        default_out = str(Path.cwd() / f"{slug_str}.overlay")
        out_path_str = questionary.text(
            "Output DTS file path:",
            default=default_out
        ).ask()
        
        if out_path_str is None:
            return
        out_path = Path(out_path_str)

        # Generate overlay
        generate_dts_overlay(slug_str, type_id_str, out_path, slot, selected_chips)
        console.print(f"[bold green]✔ Overlay written to {out_path}[/bold green]")

    def _chip_selection_for_overlay(self) -> list[str]:
        """Select chips from catalog for the overlay."""
        # Group by bus type for display
        i2c_chips = list_chips_by_bus("i2c")
        spi_chips = list_chips_by_bus("spi")
        root_chips = list_chips_by_bus("root")
        
        all_chips = []
        for key in i2c_chips + spi_chips + root_chips:
            chip = CHIP_CATALOG[key]
            all_chips.append(f"[{chip['bus'].upper()}] {key} - {chip['description']} ({chip['address']})")
        
        if not all_chips:
            console.print("[yellow]No chips in catalog[/yellow]")
            return []
        
        selected = questionary.checkbox(
            "Select chips to include in overlay:",
            choices=all_chips
        ).ask()
        
        if selected is None:
            return []
        
        # Extract keys
        return [s.split("] ")[1].split(" - ")[0] for s in selected]

    # ============================================================
    # REMOVE WIZARD
    # ============================================================
    def remove_wizard(self):
        self._print_header("HAT Deletion Wizard", "red")

        entries = self.registry.get_entries()
        if not entries:
            console.print("[bold yellow]Registry is empty. Nothing to remove.[/bold yellow]")
            return

        # Display registered HATs
        table = Table(title="Registered HATs")
        table.add_column("Type ID", style="bold cyan")
        table.add_column("Slug", style="bold green")
        table.add_column("Description", style="white")
        table.add_column("HW Rev", style="yellow")
        table.add_column("SW Ver", style="yellow")
        
        for h in entries:
            table.add_row(
                f"0x{h['type_id']:04X}",
                h["slug"],
                h["description"],
                str(h["hw_rev"]),
                str(h["sw_ver"])
            )
        console.print(table)

        # Select HAT to remove
        choices = [f"0x{h['type_id']:04X} : {h['slug']}" for h in entries]
        selected = questionary.select(
            "Select HAT to remove:",
            choices=choices
        ).ask()
        
        if selected is None:
            return
        
        type_id_str = selected.split(" : ")[0]
        type_id = int(type_id_str, 16)
        
        # Find the entry for confirmation
        target = next((h for h in entries if h["type_id"] == type_id), None)
        if not target:
            console.print("[red]HAT not found[/red]")
            return

        # Confirmation
        console.print()
        console.print(Panel(
            f"[bold]About to remove:[/bold]\n"
            f"  Type ID: {type_id_str}\n"
            f"  Slug: {target['slug']}\n"
            f"  Description: {target['description']}",
            title="[red]Confirm Deletion[/red]",
            border_style="red"
        ))
        
        if not self._confirm_action("Are you sure you want to delete this HAT from the registry?"):
            console.print("[yellow]Cancelled[/yellow]")
            return
        
        # Double confirmation for safety
        if not self._confirm_action("This action cannot be undone. Proceed?"):
            console.print("[yellow]Cancelled[/yellow]")
            return

        # Remove from registry
        if remove_registry_entry(self.registry, type_id):
            save_registry(REGISTRY_FILE, self.registry)
            console.print(f"[bold green]✔ Removed HAT 0x{type_id:04X} ({target['slug']}) from registry[/bold green]")
        else:
            console.print("[red]Failed to remove HAT (not found)[/red]")