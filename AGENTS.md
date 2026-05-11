# LArPix / CRS DAQ workspace

This workspace contains two repos:

- `crs-daq/`: high-level DAQ, tile configuration, pedestal, commissioning workflows.
- `larpix-control/`: low-level LArPix/PACMAN/tile/chip/controller communication.

When answering questions:
1. Treat both repos as one coupled software stack.
2. Start from `crs-daq` for operational workflows.
3. Follow calls/imports into `larpix-control`.
4. Prefer concrete file/function/class references.
5. For understanding tasks, do not edit code unless explicitly asked.
6. For code-change tasks, make minimal changes and summarize risks.

Useful commands:
```bash
find crs-daq larpix-control -name "*.py" | sort
grep -R "Controller" -n crs-daq larpix-control
grep -R "pacman" -ni crs-daq larpix-control
grep -R "pedestal" -ni crs-daq larpix-control
