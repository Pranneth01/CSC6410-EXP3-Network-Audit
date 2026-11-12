
"""
CSC6410 Experiment 3
Purpose: Collect this computer's network configuration,
validate it against the professor's JSON Schema, and report drift.

Assumptions:
- Runs on Ubuntu/Linux, including WSL.
- Uses the Linux ip command for interface and route data.
- Reads DNS servers from /etc/resolv.conf.
- WSL virtual adapters are identified as virtual.
- Intended interfaces are matched by interface name.

Limitations:
- DNS information may be managed automatically by WSL.
- This script does not inspect Windows physical network adapters.
"""

import json
import socket
import subprocess
from datetime import datetime
from pathlib import Path
from jsonschema import Draft202012Validator

# Use the folder containing this script for all input/output files.
HERE = Path(__file__).resolve().parent
SCHEMA_FILE = HERE / "host_schema.json"
INTENDED_FILE = HERE / "intended.json"
OBSERVED_FILE = HERE / "observed.json"


def run_command(command):
    """Run a Linux command and return its output."""
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout


def collect_network():
    """Collect interfaces, addresses, gateway, and DNS."""

    # Linux returns interface information in JSON format.
    links = json.loads(run_command(["ip", "-j", "addr", "show"]))

    # Detect whether this Linux system runs inside WSL.
    try:
        environment = run_command(
            ["systemd-detect-virt"]
        ).strip()
    except subprocess.CalledProcessError:
        environment = "none"

    interfaces = []

    for link in links:
        name = link["ifname"]
        flags = link.get("flags", [])

        # Convert Linux interface types into model values.
        if name == "lo":
            interface_type = "loopback"
        elif environment == "wsl":
            interface_type = "virtual"
        elif link.get("link_type") == "ether":
            interface_type = "ethernet"
        elif "wlan" in name.lower() or "wifi" in name.lower():
            interface_type = "wifi"
        else:
            interface_type = "other"

        # Linux uses several status values; the model allows up/down.
        status = "up" if "UP" in flags else "down"

        interface = {
            "name": name,
            "type": interface_type,
            "oper-status": status,
            "mtu": link.get("mtu")
        }

        # Convert MAC addresses to lowercase colon-separated format.
        mac = link.get("address")
        if mac:
            interface["mac"] = mac.lower()

        ipv4 = []
        ipv6 = []

        # Add prefix lengths to each IP address.
        for address in link.get("addr_info", []):
            family = address.get("family")
            ip = address.get("local")
            prefix = address.get("prefixlen")

            if not ip or prefix is None:
                continue

            value = f"{ip}/{prefix}"

            if family == "inet":
                ipv4.append(value)
            elif family == "inet6":
                ipv6.append(value)

        interface["ipv4"] = ipv4
        interface["ipv6"] = ipv6
        interfaces.append(interface)

    # Find the default gateway from the routing table.
    routes = json.loads(
        run_command(["ip", "-j", "route", "show", "default"])
    )

    gateway = routes[0].get("gateway") if routes else None

    # Read DNS server addresses from the resolver configuration.
    dns_servers = []
    with open("/etc/resolv.conf", "r") as file:
        for line in file:
            parts = line.split()
            if len(parts) >= 2 and parts[0] == "nameserver":
                dns_servers.append(parts[1])

    host = {
        "hostname": socket.gethostname(),
        "os": "linux",
        "collected-at": datetime.now().astimezone().isoformat(),
        "dns-server": dns_servers,
        "interface": interfaces
    }

    if gateway:
        host["default-gateway"] = gateway

    return {"student-host:host": host}


def validate_configuration(observed, schema):
    """Validate observed configuration and print every schema error."""

    validator = Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(observed),
        key=lambda error: list(map(str, error.absolute_path))
    )

    print("\n--- SCHEMA VALIDATION ---")

    if not errors:
        print("VALID: observed.json matches host_schema.json")
    else:
        print(f"INVALID: {len(errors)} error(s) found")
        for error in errors:
            path = "/" + "/".join(
                str(item) for item in error.absolute_path
            )
            print(f"Path: {path} | Error: {error.message}")

    return errors


def report_drift(intended, observed):
    """Compare intended values with observed values.
    Interfaces are matched by name, not by list position.
    """

    print("\n--- CONFIGURATION DRIFT REPORT ---")

    expected_host = intended["student-host:host"]
    actual_host = observed["student-host:host"]
    differences = 0

    # Compare host-level fields included in intended.json.
    for field, expected in expected_host.items():
        if field == "interface":
            continue

        actual = actual_host.get(field, "<missing>")

        if expected != actual:
            print(
                f"{field}: intended {expected}, observed {actual}"
            )
            differences += 1

    # Match interfaces using their names.
    actual_interfaces = {
        item["name"]: item
        for item in actual_host.get("interface", [])
    }

    for expected_interface in expected_host.get("interface", []):
        name = expected_interface["name"]
        actual_interface = actual_interfaces.get(name)

        if actual_interface is None:
            print(
                f"interface {name}: intended present, "
                "observed missing"
            )
            differences += 1
            continue

        # Compare only fields explicitly specified in intended.json.
        for field, expected in expected_interface.items():
            if field == "name":
                continue

            actual = actual_interface.get(field, "<missing>")

            if expected != actual:
                print(
                    f"interface {name} / {field}: "
                    f"intended {expected}, observed {actual}"
                )
                differences += 1

    if differences == 0:
        print("No drift found. Intended values match observed values.")

    print(f"Total differences: {differences}")


def main():
    """Load files, collect data, validate, and report drift."""

    print("CSC6410 EXP3 - Network Configuration Audit")

    with open(SCHEMA_FILE) as file:
        schema = json.load(file)

    with open(INTENDED_FILE) as file:
        intended = json.load(file)

    observed = collect_network()

    # Save collected configuration as JSON.
    with open(OBSERVED_FILE, "w") as file:
        json.dump(observed, file, indent=2)

    print(f"\nObserved configuration saved to {OBSERVED_FILE}")

    # Validate the collected data against the professor's schema.
    validate_configuration(observed, schema)

    # Compare observed values against the intended configuration.
    report_drift(intended, observed)


if __name__ == "__main__":
    main()
