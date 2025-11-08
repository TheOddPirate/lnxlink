import subprocess
import logging
import shutil
from typing import List, Optional

from lnxlink.modules.scripts.helpers import can_run_command_without_sudo


logger = logging.getLogger("lnxlink")


def is_installed(binary_name: str) -> bool:
    return shutil.which(binary_name) is not None


def is_aur_package(pkg_name: str) -> bool:
    # Hvis pamac finnes, bruk den for Manjaro
    pamac = shutil.which("pamac")
    if pamac:
        try:
            out = subprocess.check_output([pamac, "search", "-a", pkg_name], text=True)
            for line in out.splitlines():
                if line.startswith(pkg_name) and "AUR" in line:
                    return True
            return False
        except Exception:
            pass

    # Hvis pacman finnes, sjekk offisiell repo
    pacman = shutil.which("pacman")
    if pacman:
        result = subprocess.run([pacman, "-Si", pkg_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return result.returncode != 0  # returncode != 0 -> finnes ikke i repo -> AUR

    # Default: ikke Arch
    logger.warning("Cannot detect AUR package: no pacman/pamac found")
    return False


def detect_package_manager() -> Optional[str]:
    """Returner navnet på tilgjengelig pakkehåndterer eller None."""
    candidates = ["apt-get", "apt", "dnf", "yum", "pamac", "pacman", "zypper", "apk"]
    for c in candidates:
        if shutil.which(c):
            # prefer apt-get over apt if both present
            if c == "apt" and shutil.which("apt-get"):
                continue
            elif c == "pacman" and shutil.which("pamac"):
                continue
            return c
    return None


def build_install_commands(packages: List[str]) -> Optional[List[List[str]]]:
    """
    Build a safe command list for subprocess to install packages.

    - Offisiell repo: prepend 'sudo -n'
    - AUR (pacman/pamac): run with yay/trizen as normal user (no sudo)
    - Returns None if installation cannot run non-interactively
    """
    if not packages:
        logger.warning("No package list given, aborting")
        return None
    if isinstance(packages, str):
        packages = [packages]

    pkg_mgr = detect_package_manager()
    if not pkg_mgr:
        logger.error("No package manager detected on this system.")
        return None

    # Check sudo access for official package manager
    if not can_run_command_without_sudo(pkg_mgr):
        logger.warning(
            f"Package manager '{pkg_mgr}' requires sudo password. "
            "This command will fail non-interactively without updating visudo."
        )
        return None

    cmds = []

    for pkg in packages:
        # Arch/Manjaro logic for pacman/pamac
        if pkg_mgr in ("pacman", "pamac") and is_aur_package(pkg):
            aur_helper = shutil.which("yay") or shutil.which("trizen")
            if not aur_helper:
                logger.error(f"AUR package '{pkg}' detected but no AUR helper found.")
                return None
            # AUR packages are run as user (no sudo)
            cmds.append([aur_helper, "-S", "--noconfirm", pkg])
        else:
            # Official repo packages: prepend sudo -n
            if pkg_mgr in ("apt-get", "apt"):
                cmds.append(["sudo", "-n", pkg_mgr, "update", "&&", pkg_mgr, "install", "-y", pkg])
            elif pkg_mgr in ("dnf", "yum"):
                cmds.append(["sudo", "-n", pkg_mgr, "install", "-y", pkg])
            elif pkg_mgr in ("pacman", "pamac"):
                cmds.append(["sudo", "-n", pkg_mgr, "-S", "--noconfirm", pkg])
            elif pkg_mgr == "apk":
                cmds.append(["sudo", "-n", "apk", "add", "--no-cache", pkg])
            else:
                cmds.append(["sudo", "-n", pkg_mgr, "install", pkg])  # fallback

    return cmds
