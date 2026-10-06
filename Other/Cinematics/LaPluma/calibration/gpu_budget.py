"""
How much of the graphics card a calibration job may take.

The card is shared with the user's own work (Blender open beside the
fits): a job claims what is free when it starts, less ``RESERVE`` kept for
that work, and never more than ``SHARE`` of the card.  The claim is set as
the process's hard cap, so a job that outgrows it fails at once rather than
spilling into shared system memory, which slows the whole machine to a
crawl.  Jobs size their batches from the claim (``chunk``) and run one at a
time.
"""
import torch

GIGABYTE = 1024 ** 3
RESERVE = 3 * GIGABYTE
SHARE = 0.55


def claim(least=GIGABYTE // 2, reserve=RESERVE, share=SHARE):
    """Cap this process to its share of what is free and return the budget in bytes; refuse
    to start when less than ``least`` can be had."""
    free, total = torch.cuda.mem_get_info()
    budget = int(max(0, min(free - reserve, share * total)))
    if budget < least:
        raise SystemExit(f"the card is busy: {free / GIGABYTE:.1f} GB free of {total / GIGABYTE:.1f} GB, "
                         f"{reserve / GIGABYTE:.1f} GB kept for other work, {least / GIGABYTE:.1f} GB needed")
    torch.cuda.set_per_process_memory_fraction(budget / total)
    print(f"[gpu] claimed {budget / GIGABYTE:.1f} GB of {total / GIGABYTE:.1f} GB ({free / GIGABYTE:.1f} GB free)", flush=True)
    return budget


def chunk(budget, bytes_each, resident=0, most=None, headroom=0.6):
    """How many units of work, ``bytes_each`` apiece, fit the budget beside ``resident`` bytes."""
    count = max(1, int((budget * headroom - resident) // max(bytes_each, 1)))
    return min(count, most) if most else count
